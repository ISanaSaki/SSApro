import asyncio
import logging
import time

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


async def _request(client: httpx.AsyncClient, settings: Settings, method: str, url: str,
                   params: dict | None = None, body: dict | None = None) -> tuple[int, dict | None]:
    """Bounded retry on 429/503 honoring Retry-After; other failures retried once without sleep."""
    last = (0, None)
    for attempt in range(settings.http_max_retries):
        try:
            resp = await client.request(method, url, params=params, json=body, timeout=settings.http_timeout_sec)
        except httpx.HTTPError as exc:
            logger.warning("kit request failed %s %s: %s", method, url, exc)
            last = (0, None)
            continue
        if resp.status_code in (429, 503):
            try:
                wait = float(resp.headers.get("Retry-After", 1.0))
            except ValueError:
                wait = 1.0
            await asyncio.sleep(min(max(wait, 0.2), 5.0))
            last = (resp.status_code, None)
            continue
        try:
            payload = resp.json() if resp.content else None
        except ValueError:
            payload = None
        return resp.status_code, payload
    return last


class SendResult:
    def __init__(self, accepted: bool, status: int, duplicate: bool):
        self.accepted = accepted
        self.status = status
        self.duplicate = duplicate


class DispatchResult:
    def __init__(self, created: bool, replay: bool, error: str | None):
        self.created = created
        self.replay = replay
        self.error = error


class ClockClient:
    """Only source of simulation time for the whole service."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self._settings = settings
        self._client = client
        self._lock = asyncio.Lock()
        self._cached: dict = {"sim_time": 0.0, "epoch": "2027-01-15T00:00:00+03:30", "speed": 1.0}
        self._fetched_at = 0.0
        self._healthy = True

    async def _refresh(self) -> None:
        if time.monotonic() - self._fetched_at < self._settings.clock_cache_ttl_sec:
            return
        async with self._lock:
            if time.monotonic() - self._fetched_at < self._settings.clock_cache_ttl_sec:
                return
            status, payload = await _request(self._client, self._settings, "GET",
                                             self._settings.gateway_url + "/clock")
            if status == 200 and isinstance(payload, dict) and "sim_time" in payload:
                self._cached = payload
                self._fetched_at = time.monotonic()
                if not self._healthy:
                    logger.info("gateway clock recovered")
                self._healthy = True
            else:
                if self._healthy:
                    logger.warning("gateway clock unavailable (status=%s); using cached sim_time=%.1f",
                                   status, self._cached["sim_time"])
                self._healthy = False

    async def now_sim(self) -> float:
        await self._refresh()
        return float(self._cached["sim_time"])

    async def payload(self) -> dict:
        await self._refresh()
        return dict(self._cached)


class GatewayClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self._settings = settings
        self._client = client

    async def send_message(self, body: dict) -> SendResult:
        status, payload = await _request(self._client, self._settings, "POST",
                                         self._settings.gateway_url + "/messages", body=body)
        if status in (200, 202):
            return SendResult(accepted=True, status=status, duplicate=False)
        if status == 409:
            return SendResult(accepted=False, status=status, duplicate=True)
        logger.warning("gateway message rejected status=%s body=%s", status, body)
        return SendResult(accepted=False, status=status, duplicate=False)


class InventoryClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self._settings = settings
        self._client = client

    async def get_inventory(self) -> dict:
        status, payload = await _request(self._client, self._settings, "GET",
                                         self._settings.inventory_url + "/inventory")
        if status == 200 and isinstance(payload, dict) and isinstance(payload.get("items"), list):
            return payload
        logger.warning("inventory snapshot unavailable status=%s", status)
        return {"sim_time": 0.0, "items": []}

    async def dispatch(self, body: dict) -> DispatchResult:
        status, payload = await _request(self._client, self._settings, "POST",
                                         self._settings.inventory_url + "/inventory/dispatch", body=body)
        if status == 201:
            return DispatchResult(created=True, replay=False, error=None)
        if status == 200:
            return DispatchResult(created=False, replay=True, error=None)
        code = None
        if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
            code = payload["error"].get("code")
        logger.warning("inventory dispatch failed status=%s dispatch_id=%s error=%s",
                       status, body.get("dispatch_id"), code)
        return DispatchResult(created=False, replay=False, error=code)


class TravelClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self._settings = settings
        self._client = client

    async def minutes(self, from_lat: float, from_lon: float, to_lat: float, to_lon: float) -> float | None:
        params = {"from": f"{from_lat},{from_lon}", "to": f"{to_lat},{to_lon}"}
        status, payload = await _request(self._client, self._settings, "GET",
                                         self._settings.travel_url + "/travel", params=params)
        if status == 200 and isinstance(payload, dict) and isinstance(payload.get("minutes"), (int, float)):
            return float(payload["minutes"])
        logger.warning("travel lookup failed status=%s from=(%s,%s) to=(%s,%s)",
                       status, from_lat, from_lon, to_lat, to_lon)
        return None
