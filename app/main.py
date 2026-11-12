import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.deps import build_services
from app.api.routers import callbacks, health, requests as requests_router, ui
from app.config import Settings, load_settings
from app.domain.ranking import TravelTimeRankingStrategy
from app.ports.clients import ClockClient, GatewayClient, InventoryClient, TravelClient
from app.tasks.dispatcher import BackgroundDispatcher

logger = logging.getLogger("app.main")

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def setup_logging(settings: Settings) -> None:
    logs_dir = BASE_DIR / "logs"
    logs_dir.mkdir(exist_ok=True)
    handlers = [
        logging.StreamHandler(),
        logging.FileHandler(logs_dir / "service.log", encoding="utf-8"),
    ]
    for handler in handlers:
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logging.basicConfig(level=settings.log_level.upper(), handlers=handlers, force=True)


def build_ranking_strategy(settings: Settings):
    if settings.ranking_strategy != "ai_response":
        return TravelTimeRankingStrategy()
    try:
        from app.ai.ranking import AIResponseRankingStrategy
        return AIResponseRankingStrategy(settings.ai_model_path)
    except Exception as exc:
        logger.warning("ai_response strategy unavailable (%s); falling back to travel_time", exc)
        return TravelTimeRankingStrategy()


def create_app() -> FastAPI:
    settings = load_settings()
    setup_logging(settings)
    app = FastAPI(title="BloodNet", docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=400,
                            content={"error": {"code": "validation_error",
                                               "message": "invalid request body"}})

    @app.exception_handler(HTTPException)
    async def http_error_handler(request: Request, exc: HTTPException):
        detail = exc.detail
        if isinstance(detail, dict) and "error" in detail:
            content = detail
        else:
            content = {"error": {"code": "internal_error", "message": str(detail)}}
        return JSONResponse(status_code=exc.status_code, content=content,
                            headers=exc.headers or {})

    @app.exception_handler(Exception)
    async def internal_error_handler(request: Request, exc: Exception):
        logger.exception("unhandled error")
        return JSONResponse(status_code=500,
                            content={"error": {"code": "internal_error",
                                               "message": "unexpected error"}})

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from app.data.database import create_all, init_engine
        from app.data.loader import load_kit_data

        engine = init_engine(settings)
        await create_all(engine)
        kit_data = await load_kit_data(settings, engine)
        client = httpx.AsyncClient()
        clock = ClockClient(settings, client)
        app.state.settings = settings
        app.state.kit_data = kit_data
        app.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        app.state.clock = clock
        app.state.gateway = GatewayClient(settings, client)
        app.state.inventory = InventoryClient(settings, client)
        app.state.travel = TravelClient(settings, client)
        app.state.ranking_strategy = build_ranking_strategy(settings)
        dispatcher = BackgroundDispatcher(
            settings, clock, app.state.sessionmaker,
            lambda session: build_services(session, app.state))
        app.state.dispatcher = dispatcher
        dispatcher.start()
        logger.info("BloodNet service started on :%s (kit=%s)", settings.port, settings.kit_path)
        try:
            yield
        finally:
            await dispatcher.stop()
            await client.aclose()
            await engine.dispose()

    app.router.lifespan_context = lifespan
    app.include_router(health.router)
    app.include_router(requests_router.router)
    app.include_router(callbacks.router)
    app.include_router(ui.router)

    static_dir = BASE_DIR / "static"
    if static_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=load_settings().port)
