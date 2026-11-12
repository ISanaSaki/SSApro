STATUSES = ["pending_review", "open", "mobilizing", "partially_fulfilled", "fulfilled", "cancelled", "expired"]
EVENTS = ["approved", "wave_started", "first_fulfilled", "fully_fulfilled", "cancelled", "expired"]

TRANSITIONS = {
    ("pending_review", "approved"): "open",
    ("open", "wave_started"): "mobilizing",
    ("open", "first_fulfilled"): "partially_fulfilled",
    ("mobilizing", "first_fulfilled"): "partially_fulfilled",
    ("open", "fully_fulfilled"): "fulfilled",
    ("mobilizing", "fully_fulfilled"): "fulfilled",
    ("partially_fulfilled", "fully_fulfilled"): "fulfilled",
    ("open", "cancelled"): "cancelled",
    ("mobilizing", "cancelled"): "cancelled",
    ("partially_fulfilled", "cancelled"): "cancelled",
    ("open", "expired"): "expired",
    ("mobilizing", "expired"): "expired",
    ("partially_fulfilled", "expired"): "expired",
}

TERMINAL = {"fulfilled", "cancelled", "expired"}
AMENDABLE = {"open", "mobilizing", "partially_fulfilled"}


class InvalidTransitionError(Exception):
    def __init__(self, current: str, event: str):
        super().__init__(f"invalid transition: {event} from {current}")
        self.current = current
        self.event = event


def transition(current: str, event: str) -> str:
    if event not in EVENTS:
        raise InvalidTransitionError(current, event)
    target = TRANSITIONS.get((current, event))
    if target is None:
        raise InvalidTransitionError(current, event)
    return target


def is_terminal(status: str) -> bool:
    return status in TERMINAL


def is_amendable(status: str) -> bool:
    return status in AMENDABLE
