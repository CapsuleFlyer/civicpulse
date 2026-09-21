"""Application factory, lifespan and graceful shutdown."""

from __future__ import annotations

import asyncio
import logging
import signal
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.bootstrap import attach_state, close_state
from app.config import Settings, get_settings
from app.logging_setup import configure_logging
from app.metrics import INFLIGHT
from app.middleware import RequestContextMiddleware
from app.routes import complaints, health, meta, stats

logger = logging.getLogger("civicpulse.app")

DESCRIPTION = """
Municipal complaint intake, triage and operations.

A citizen submits free text. The backend validates it, triages it into a
category, a priority and a one-line summary through a replaceable provider,
persists it, and serves it to an operations dashboard.
"""


def install_signal_handlers(app: FastAPI) -> None:
    """Drain on SIGTERM.

    Flipping `draining` makes /ready return 503, which removes this pod from the
    Service endpoints *before* the server stops accepting connections. The
    previous handler (uvicorn's) is then chained so the normal shutdown — finish
    in-flight requests, run the lifespan teardown, close the pool — still runs.
    Without this, every rolling update drops live requests.
    """
    previous = signal.getsignal(signal.SIGTERM)

    def handler(signum, frame):  # pragma: no cover - exercised via unit test below
        app.state.draining = True
        logger.info("sigterm_received", extra={"inflight": INFLIGHT._value.get()})
        if callable(previous):
            previous(signum, frame)

    try:
        signal.signal(signal.SIGTERM, handler)
    except ValueError:
        # Not the main thread (tests, embedded runs). Nothing to install.
        logger.debug("sigterm_handler_skipped")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    install_signal_handlers(app)
    logger.info(
        "startup",
        extra={
            "environment": settings.environment,
            "triage_provider": app.state.triage_service.provider_name,
            "version": __version__,
        },
    )
    yield
    app.state.draining = True
    # Give in-flight work a moment to finish before the pool disappears.
    for _ in range(50):
        if INFLIGHT._value.get() <= 1:
            break
        await asyncio.sleep(0.1)
    await close_state(app)
    logger.info("shutdown_complete")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        # FastAPI's default is 422; the contract says 400 with a field-level body.
        fields = [
            {
                "field": ".".join(str(part) for part in error["loc"][1:]) or str(error["loc"][0]),
                "message": error["msg"],
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=400,
            content={
                "error": "validation_error",
                "message": "the submission was rejected: " + "; ".join(f["field"] for f in fields),
                "fields": fields,
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail
        body = detail if isinstance(detail, dict) else {"error": "http_error", "message": str(detail)}
        headers = dict(exc.headers or {})
        if exc.status_code == 429 and isinstance(detail, dict):
            headers["Retry-After"] = str(detail.get("retry_after", 60))
        return JSONResponse(status_code=exc.status_code, content=body, headers=headers)

    @app.exception_handler(Exception)
    async def unhandled_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_exception", extra={"error_class": type(exc).__name__})
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "message": "the request could not be completed"},
        )


def create_app(settings: Settings | None = None, **state_overrides) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="CivicPulse API",
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
        openapi_url="/api/openapi.json",
        docs_url="/api/docs",
    )
    attach_state(app, settings, **state_overrides)

    app.add_middleware(RequestContextMiddleware)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
            allow_headers=["Content-Type", "X-Request-ID"],
            expose_headers=["X-Cache", "X-Request-ID", "Retry-After"],
        )

    register_exception_handlers(app)
    app.include_router(complaints.router)
    app.include_router(stats.router)
    app.include_router(meta.router)
    app.include_router(health.router)
    return app


app = create_app()
