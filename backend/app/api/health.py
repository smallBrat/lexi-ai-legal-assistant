"""Health check endpoint for the Lexi AI Legal Assistant API."""

from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])


@router.get(
    "",
    summary="Health check endpoint",
    description="Return the health status of the Lexi AI Legal Assistant API.",
    tags=["health"],
)
async def health_check() -> dict[str, str]:
    """Return the health status of the API.

    Returns:
        Lightweight JSON response with service status.
    """
    return {
        "status": "ok",
        "service": "lexi-ai-backend",
    }