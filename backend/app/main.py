"""Main entry point for the Lexi AI Legal Assistant FastAPI backend."""

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.health import router as health_router
from app.api.router import register_routers
from app.core.config import get_settings
from app.core.logging import debug, error, info
from app.core.middleware import add_security_headers


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance.
    """
    settings = get_settings()

    app = FastAPI(
        title="Lexi AI Legal Assistant API",
        version="1.0.0",
        description="A GenAI-powered legal assistant backend",
        debug=settings.is_development(),
    )

    # CORS allowlist: dev localhost origins plus the configured frontend
    # origin (FRONTEND_URL) for production deployments.
    cors_origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    if settings.FRONTEND_URL:
        cors_origins.append(settings.FRONTEND_URL.rstrip("/"))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Accept",
            "Origin",
            "X-Requested-With",
        ],
        max_age=600,
    )

    # Phase 15: conservative security headers on every response.
    add_security_headers(app)

    # Register API routers
    register_routers(app)

    # Include health check router
    app.include_router(health_router)

    # Add root endpoint
    @app.get(
        "/",
        summary="Root endpoint",
        description="Return API metadata and welcome information",
    )
    async def root() -> dict[str, str]:
        """Return the API root endpoint with metadata.

        Returns:
            JSON containing API metadata including name, version,
            and environment information.
        """
        return {
            "message": "Welcome to Lexi AI Legal Assistant API",
            "title": "Lexi AI Legal Assistant API",
            "version": "1.0.0",
            "environment": settings.ENVIRONMENT,
        }

    # TEMPORARY: log every RequestValidationError before returning the
    # normal 422 so we can see the exact validation failure.
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        body: bytes | None = None
        try:
            body = await request.body()
        except Exception as exc_read:
            debug("Failed to read request body for validation error", exc=repr(exc_read))

        # Extract path params from the request scope (set by Starlette routing).
        path_params: dict[str, str] = {}
        try:
            path_params = dict(request.path_params) if request.path_params else {}
        except Exception:
            pass

        # Redact Authorization header for safe logging.
        auth_header = request.headers.get("authorization", "(none)")
        if auth_header.startswith("Bearer "):
            auth_header = "Bearer <redacted>"

        # Phase 15: never log raw request bodies — uploads and chat payloads
        # contain user document text and PII. Log only metadata.
        error(
            "[422 VALIDATION]",
            method=request.method,
            path=str(request.url.path),
            path_params=path_params,
            query=str(request.url.query) or "(none)",
            content_type=request.headers.get("content-type", "(none)"),
            authorization=auth_header,
            body_length=len(body) if body else 0,
            errors=exc.errors(),
        )
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors(), "type": "request_validation_error"},
        )

    # Startup log
    debug("Lexi AI Legal Assistant API starting up")
    info(
        "Application initialized",
        environment=settings.ENVIRONMENT,
        version="1.0.0",
    )

    return app


app = create_app()


# Allow running directly with: python -m app.main
if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "app.main:create_app",
        host="0.0.0.0",
        port=8000,
        reload=settings.is_development(),
        factory=True,
    )