import pytest

from app.domain.state_machine import (AMENDABLE, EVENTS, STATUSES, TERMINAL, TRANSITIONS,
                                      InvalidTransitionError, is_amendable, is_terminal,
                                      transition)


def test_all_valid_transitions():
    for (current, event), target in TRANSITIONS.items():
        assert transition(current, event) == target


def test_all_invalid_transitions_raise():
    for status in STATUSES:
        for event in EVENTS:
            if (status, event) in TRANSITIONS:
                continue
            with pytest.raises(InvalidTransitionError):
                transition(status, event)


def test_unknown_event_raises():
    with pytest.raises(InvalidTransitionError):
        transition("open", "nonsense")


def test_terminal_statuses():
    assert is_terminal("fulfilled") and is_terminal("cancelled") and is_terminal("expired")
    for status in STATUSES:
        assert is_terminal(status) == (status in TERMINAL)


def test_amendable_statuses():
    assert is_amendable("open") and is_amendable("mobilizing")
    assert is_amendable("partially_fulfilled")
    for status in STATUSES:
        assert is_amendable(status) == (status in AMENDABLE)
