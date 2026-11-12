import asyncio
import json
import logging

from app.data.models import Event, Task
from app.domain.state_machine import InvalidTransitionError, is_terminal, transition

logger = logging.getLogger(__name__)


class BackgroundDispatcher:
    def __init__(self, settings, clock, sessionmaker, build_services):
        self._settings = settings
        self._clock = clock
        self._sessionmaker = sessionmaker
        self._build_services = build_services
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="background-dispatcher")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        while True:
            try:
                await self._tick()
            except Exception:
                logger.exception("dispatcher tick failed")
            await asyncio.sleep(self._settings.dispatcher_tick_sec)

    async def _tick(self) -> None:
        async with self._sessionmaker() as session:
            services = self._build_services(session)
            try:
                sim = await self._clock.now_sim()
                for task in await services.task_repo.pop_due(sim, limit=50):
                    try:
                        await self._handle(services, task, sim)
                        await services.task_repo.finish(task.id, True)
                    except Exception:
                        logger.exception("task failed id=%s type=%s request=%s", task.id,
                                         task.task_type, task.request_id)
                        await services.task_repo.finish(task.id, False)
                await services.sla_service.check_expired(sim)
                await self._deliver_stock(services, sim)
                await session.commit()
            except BaseException:
                await session.rollback()
                raise

    async def _handle(self, services, task: Task, sim: float) -> None:
        if task.task_type == "send_wave":
            await self._handle_send_wave(services, task, sim)
        elif task.task_type == "reminder":
            await self._handle_reminder(services, task, sim)
        elif task.task_type == "stop_outreach":
            payload = json.loads(task.payload_json or "{}")
            await services.invitation_service.stop_outreach(task.request_id,
                                                            payload.get("template", "cancelled"))
        elif task.task_type == "alloc_retry":
            await self._handle_alloc_retry(services, task, sim)

    async def _handle_send_wave(self, services, task: Task, sim: float) -> None:
        r = await services.request_repo.get(task.request_id)
        if r is None or is_terminal(r.status):
            return
        await services.allocation_service.allocate(task.request_id, sim)
        await services.invitation_service.build_wave(task.request_id, sim)
        r = await services.request_repo.get(task.request_id)
        if r is None or is_terminal(r.status):
            return
        if r.needed - r.fulfilled - r.stock_inflight > 0:
            if r.wave_count < self._settings.wave_max_count:
                await self._push(services, "send_wave", task.request_id, sim,
                                 sim + self._settings.wave_interval_min)
            else:
                await self._push(services, "reminder", task.request_id, sim,
                                 sim + self._settings.reminder_interval_min)
                await self._push(services, "alloc_retry", task.request_id, sim,
                                 sim + self._settings.alloc_retry_interval_min)

    async def _handle_reminder(self, services, task: Task, sim: float) -> None:
        r = await services.request_repo.get(task.request_id)
        if r is None or is_terminal(r.status):
            return
        await services.invitation_service.send_reminders(task.request_id, sim)
        if r.needed - r.fulfilled - r.stock_inflight > 0:
            await self._push(services, "reminder", task.request_id, sim,
                             sim + self._settings.reminder_interval_min)

    async def _handle_alloc_retry(self, services, task: Task, sim: float) -> None:
        await services.allocation_service.allocate(task.request_id, sim)
        r = await services.request_repo.get(task.request_id)
        if r is None or is_terminal(r.status):
            return
        if r.needed - r.fulfilled - r.stock_inflight > 0:
            await self._push(services, "alloc_retry", task.request_id, sim,
                             sim + self._settings.alloc_retry_interval_min)

    async def _push(self, services, task_type: str, request_id: str, sim: float,
                    next_attempt: float, payload: dict | None = None) -> None:
        await services.task_repo.push(Task(
            task_type=task_type, request_id=request_id,
            payload_json=json.dumps(payload or {}),
            status="pending", attempts=0,
            created_sim_min=sim, next_attempt_sim_min=next_attempt))

    async def _deliver_stock(self, services, sim: float) -> None:
        for d in await services.dispatch_repo.due_deliveries(sim):
            event = Event(
                event_id="sd-" + d.dispatch_id, request_id=d.request_id, donor_id=None,
                notification_id=None, kind="stock_delivery", response=None, event=None,
                status=None, reason=None, sim_time=sim, received_at_sim_min=sim)
            if not await services.event_repo.add_or_ignore(event):
                continue
            r = await services.request_repo.get(d.request_id)
            if r is None:
                continue
            r.stock_inflight = max(0, r.stock_inflight - d.units)
            was_zero = r.fulfilled == 0
            r.fulfilled += d.units
            r.updated_sim_min = sim
            if not is_terminal(r.status):
                try:
                    if was_zero:
                        r.status = transition(r.status, "first_fulfilled")
                    if r.fulfilled >= r.needed:
                        r.status = transition(r.status, "fully_fulfilled")
                except InvalidTransitionError:
                    pass
            await services.request_repo.update(r)
            if r.status == "fulfilled":
                await services.invitation_service.stop_outreach(d.request_id, "not_needed")
