"""The state machine, exhaustively. Every pair of statuses is asserted."""

import itertools

import pytest

from app.domain import TERMINAL_STATUSES, TRANSITIONS, InvalidTransition, Status, assert_can_transition

EXPECTED_ALLOWED = {
    (Status.OPEN, Status.IN_PROGRESS),
    (Status.OPEN, Status.REJECTED),
    (Status.IN_PROGRESS, Status.RESOLVED),
    (Status.IN_PROGRESS, Status.REJECTED),
}


@pytest.mark.parametrize("current,requested", list(itertools.product(Status, Status)))
def test_every_pair_matches_the_specification(current: Status, requested: Status) -> None:
    if (current, requested) in EXPECTED_ALLOWED:
        assert_can_transition(current, requested)
    else:
        with pytest.raises(InvalidTransition):
            assert_can_transition(current, requested)


def test_terminal_states_are_terminal() -> None:
    assert TERMINAL_STATUSES == {Status.RESOLVED, Status.REJECTED}
    for status in TERMINAL_STATUSES:
        assert TRANSITIONS[status] == frozenset()


def test_invalid_transition_carries_the_allowed_set() -> None:
    with pytest.raises(InvalidTransition) as exc_info:
        assert_can_transition(Status.RESOLVED, Status.OPEN)
    assert exc_info.value.current is Status.RESOLVED
    assert exc_info.value.requested is Status.OPEN
    assert exc_info.value.allowed == []
