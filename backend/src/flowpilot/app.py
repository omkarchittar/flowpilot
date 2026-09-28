"""FastAPI application factory with operational endpoints and safe error envelopes."""

import json
import logging
import re
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from flowpilot.config import Settings
from flowpilot.db import Database

logger = logging.getLogger("flowpilot.requests")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    database = Database(settings.database_url)
    registry = CollectorRegistry()
    requests = Counter(
        "flowpilot_http_requests_total",
        "HTTP responses",
        ["method", "route", "status"],
        registry=registry,
    )
    latency = Histogram(
        "flowpilot_http_duration_seconds",
        "HTTP response time",
        ["method", "route"],
        registry=registry,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        database.close()

    app = FastAPI(title="FlowPilot API", version="0.1.0", lifespan=lifespan)
    app.state.database = database
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "Idempotency-Key"],
        expose_headers=["X-Request-ID"],
    )

    def error(request: Request, code: str, message: str, status: int) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": code, "message": message, "request_id": request.state.request_id}},
            status_code=status,
        )

    @app.middleware("http")
    async def observe(request: Request, call_next):
        supplied = request.headers.get("X-Request-ID", "")
        request.state.request_id = (
            supplied if re.fullmatch(r"[A-Za-z0-9_-]{1,100}", supplied) else str(uuid4())
        )
        started = perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            # Exception messages can contain SQL parameters, credentials or input.
            logger.error(
                json.dumps(
                    {
                        "event": "request_failed",
                        "request_id": request.state.request_id,
                        "exception_type": type(exc).__name__,
                    }
                )
            )
            response = error(request, "internal_error", "The request could not be completed.", 500)
        elapsed = perf_counter() - started
        route = getattr(request.scope.get("route"), "path", "unmatched")
        method = (
            request.method
            if request.method in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}
            else "OTHER"
        )
        requests.labels(method, route, str(response.status_code)).inc()
        latency.labels(method, route).observe(elapsed)
        logger.info(
            json.dumps(
                {
                    "event": "http_request",
                    "request_id": request.state.request_id,
                    "method": method,
                    "route": route,
                    "status": response.status_code,
                    "duration_ms": round(elapsed * 1000, 2),
                }
            )
        )
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return error(request, f"http_{exc.status_code}", str(exc.detail), exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Do not echo Pydantic's input field: it can contain passwords and documents.
        return error(request, "invalid_request", "Request does not match the required schema.", 422)

    @app.get("/health/live", tags=["operations"])
    def live():
        return {"status": "ok", "service": "flowpilot", "version": "0.1.0"}

    @app.get("/health/ready", tags=["operations"])
    def ready(request: Request):
        try:
            with database.transaction() as db:
                db.execute(text("SELECT 1"))
                # A reachable but unmigrated database is not ready for traffic.
                db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        except SQLAlchemyError:
            return error(request, "database_unavailable", "Database is not ready.", 503)
        return {"status": "ready", "service": "flowpilot"}

    @app.get("/metrics", include_in_schema=False)
    def metrics():
        return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

    return app
