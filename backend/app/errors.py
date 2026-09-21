"""Error payloads shared by every route.

One shape for every failure: {"error": <machine code>, "message": <human>, ...}.
The frontend renders `message` verbatim — a generic "something went wrong" on a
409 hides the only useful information the server had.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from app.domain import InvalidTransition


class ProblemDetail(HTTPException):
    def __init__(self, status_code: int, error: str, message: str, **extra: Any) -> None:
        super().__init__(status_code=status_code, detail={"error": error, "message": message, **extra})


def not_found(resource: str, identifier: Any) -> ProblemDetail:
    return ProblemDetail(
        status.HTTP_404_NOT_FOUND, "not_found", f"{resource} {identifier} does not exist"
    )


def conflict_from_transition(exc: InvalidTransition) -> ProblemDetail:
    return ProblemDetail(
        status.HTTP_409_CONFLICT,
        "invalid_transition",
        f"cannot transition from {exc.current.value} to {exc.requested.value}",
        attempted={"from": exc.current.value, "to": exc.requested.value},
        allowed=[s.value for s in exc.allowed],
    )


def rate_limited(retry_after: int, limit: int, window: int) -> ProblemDetail:
    return ProblemDetail(
        status.HTTP_429_TOO_MANY_REQUESTS,
        "rate_limited",
        f"limit of {limit} submissions per {window}s exceeded; retry in {retry_after}s",
        retry_after=retry_after,
    )
