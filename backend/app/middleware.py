"""Request context: correlation id, structured access log, metrics, drain counter."""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.logging_setup import request_id_var
from app.metrics import HTTP_LATENCY, HTTP_REQUESTS, INFLIGHT

logger = logging.getLogger("civicpulse.http")

REQUEST_ID_HEADER = "X-Request-ID"


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", request.url.path)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        INFLIGHT.inc()
        status_code = 500
        try:
            response: Response = await call_next(request)
            status_code = response.status_code
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            INFLIGHT.dec()
            elapsed = time.perf_counter() - started
            route = _route_template(request)
            HTTP_REQUESTS.labels(request.method, route, str(status_code)).inc()
            HTTP_LATENCY.labels(request.method, route).observe(elapsed)
            if route not in ("/metrics", "/health"):
                logger.info(
                    "http_request",
                    extra={
                        "method": request.method,
                        "route": route,
                        "path": request.url.path,
                        "status": status_code,
                        "duration_ms": round(elapsed * 1000, 2),
                        "client_ip": request.client.host if request.client else None,
                    },
                )
            request_id_var.reset(token)
