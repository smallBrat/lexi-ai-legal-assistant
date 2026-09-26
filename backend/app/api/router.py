"""Register API routers for the Lexi AI Legal Assistant."""

from fastapi import APIRouter

from app.api.analyze import router as analyze_router
from app.api.chat import router as chat_router
from app.api.compare import router as compare_router
from app.api.documents import router as documents_router
from app.api.upload import router as upload_router

# Create the main API router
api_router = APIRouter(prefix="/api", tags=["api"])


def register_routers(app) -> None:
    """Register all API routers with the FastAPI application.
    
    This function imports and includes all feature routers.
    Routers are organized by feature area for maintainability.
    
    Args:
        app: The FastAPI application instance.
    """
    # Import feature routers here to avoid circular imports
    # from app.api.v1 import users, cases, documents, etc.
    # api_router.include_router(users.router, prefix="/users", tags=["users"])
    # api_router.include_router(cases.router, prefix="/cases", tags=["cases"])
    # api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
    
    app.include_router(api_router)
    app.include_router(upload_router)
    app.include_router(analyze_router)
    app.include_router(documents_router)
    app.include_router(chat_router)
    app.include_router(compare_router)