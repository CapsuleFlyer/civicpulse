"""Domain vocabulary and the status state machine.

The transition table is data, not control flow. A chain of ifs cannot be
enumerated, tested exhaustively, or rendered to an operator; a dict can.
"""

from __future__ import annotations

from enum import StrEnum


class Category(StrEnum):
    WATER = "water"
    ELECTRICITY = "electricity"
    SANITATION = "sanitation"
    ROADS = "roads"
    STREETLIGHTS = "streetlights"
    OTHER = "other"


class Priority(StrEnum):
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class Status(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    REJECTED = "rejected"


#: The whole state machine. Terminal states map to an empty frozenset.
TRANSITIONS: dict[Status, frozenset[Status]] = {
    Status.OPEN: frozenset({Status.IN_PROGRESS, Status.REJECTED}),
    Status.IN_PROGRESS: frozenset({Status.RESOLVED, Status.REJECTED}),
    Status.RESOLVED: frozenset(),
    Status.REJECTED: frozenset(),
}

TERMINAL_STATUSES: frozenset[Status] = frozenset(
    status for status, allowed in TRANSITIONS.items() if not allowed
)


class InvalidTransition(Exception):
    """Raised when an operator attempts a transition the table forbids."""

    def __init__(self, current: Status, requested: Status) -> None:
        self.current = current
        self.requested = requested
        self.allowed = sorted(TRANSITIONS[current])
        super().__init__(f"cannot transition from {current.value} to {requested.value}")


def assert_can_transition(current: Status, requested: Status) -> None:
    if requested not in TRANSITIONS[current]:
        raise InvalidTransition(current, requested)
