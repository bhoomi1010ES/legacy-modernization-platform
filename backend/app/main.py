"""FastAPI application entrypoint for the Modernization Platform API."""

import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import api_v1_router
from app.core.config import settings
from app.core.errors import ErrorDetail, ErrorEnvelope, ErrorPayload, PlatformException


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start durable recovery without making API readiness depend on Git I/O."""
    from app.core.database import AsyncSessionLocal
    from app.services.supervisor_service import supervisor_service

    recovery_task: asyncio.Task[None] | None = None
    if settings.ENVIRONMENT != "testing":
        async def recover_after_restart() -> None:
            try:
                async with AsyncSessionLocal() as db:
                    await supervisor_service.recover_active_jobs(db)
            except asyncio.CancelledError:
                raise
            except Exception:
                # PostgreSQL remains authoritative and the explicit recovery
                # endpoint can safely retry. A single inaccessible repository
                # must not prevent health/readiness endpoints from starting.
                logger.exception("Supervisor startup reconciliation failed")

        recovery_task = asyncio.create_task(
            recover_after_restart(), name="supervisor-startup-recovery"
        )
        app.state.startup_recovery_task = recovery_task
    try:
        yield
    finally:
        if recovery_task and not recovery_task.done():
            recovery_task.cancel()
            with suppress(asyncio.CancelledError):
                await recovery_task


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # CORS configuration for browser clients
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # SEC-05 / SEC-08: Host header protection
    allowed_hosts = list(settings.ALLOWED_HOSTS or ["localhost", "127.0.0.1", "testserver"])
    if settings.ENVIRONMENT == "production":
        allowed_hosts = [h for h in allowed_hosts if h != "*"]
        if not allowed_hosts:
            allowed_hosts = ["localhost", "127.0.0.1"]
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=allowed_hosts,
    )

    # Request ID and Correlation ID middleware
    @app.middleware("http")
    async def add_request_id_middleware(request: Request, call_next):
        request_id = (
            request.headers.get("X-Request-ID")
            or request.headers.get("X-Correlation-ID")
            or f"req_{uuid4().hex[:12]}"
        )
        request.state.request_id = request_id
        request.state.correlation_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Correlation-ID"] = request_id
        return response

    # CSRF protection middleware for cookie-authenticated state-changing requests
    @app.middleware("http")
    async def csrf_protection_middleware(request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            if request.cookies.get(settings.SESSION_COOKIE_NAME) and not (
                request.url.path.endswith("/auth/login") or request.url.path.endswith("/auth/register")
            ):
                origin = request.headers.get("origin")
                referer = request.headers.get("referer")

                check_val = origin
                if not check_val and referer:
                    from urllib.parse import urlparse
                    ref_parsed = urlparse(referer)
                    check_val = f"{ref_parsed.scheme}://{ref_parsed.netloc}"

                if check_val:
                    allowed = set(settings.CORS_ALLOWED_ORIGINS)
                    host = request.headers.get("host")
                    # SEC-08: Exact origin match or exact host match (no loose substring search)
                    is_allowed = check_val in allowed
                    if not is_allowed and host:
                        from urllib.parse import urlparse
                        parsed_val = urlparse(check_val)
                        if parsed_val.netloc == host or parsed_val.hostname == host:
                            is_allowed = True
                    if not is_allowed:
                        request_id = getattr(request.state, "request_id", f"req_{uuid4().hex[:12]}")
                        payload = ErrorEnvelope(
                            error=ErrorPayload(
                                code="CSRF_FORBIDDEN",
                                message="Cross-site request forgery validation failed: untrusted origin.",
                                request_id=request_id,
                            )
                        )
                        return JSONResponse(status_code=403, content=payload.model_dump())
        return await call_next(request)

    # Global Platform Exception Handler
    @app.exception_handler(PlatformException)
    async def platform_exception_handler(request: Request, exc: PlatformException):
        request_id = getattr(request.state, "request_id", f"req_{uuid4().hex[:12]}")
        payload = ErrorEnvelope(
            error=ErrorPayload(
                code=exc.code,
                message=exc.message,
                request_id=request_id,
                details=exc.details,
            )
        )
        return JSONResponse(status_code=exc.status_code, content=payload.model_dump())

    # FastAPI Request Validation Error Handler (Consistent Envelope)
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        request_id = getattr(request.state, "request_id", f"req_{uuid4().hex[:12]}")
        details = [
            ErrorDetail(
                field=" -> ".join(str(loc) for loc in err.get("loc", [])),
                issue=err.get("msg", "Validation error"),
            )
            for err in exc.errors()
        ]
        payload = ErrorEnvelope(
            error=ErrorPayload(
                code="VALIDATION_ERROR",
                message="Request payload failed schema validation rules.",
                request_id=request_id,
                details=details,
            )
        )
        return JSONResponse(status_code=422, content=payload.model_dump())

    # Catch-all internal server error handler (Hides internal stack traces)
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", f"req_{uuid4().hex[:12]}")
        payload = ErrorEnvelope(
            error=ErrorPayload(
                code="INTERNAL_SERVER_ERROR",
                message="An unexpected server error occurred. Please contact workspace support.",
                request_id=request_id,
            )
        )
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=payload.model_dump())

    # Mount versioned API routes
    app.include_router(api_v1_router, prefix=settings.API_V1_PREFIX)

    return app


app = create_app()
