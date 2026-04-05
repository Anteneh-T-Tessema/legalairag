"""API route modules."""

from api.routers import auth_router, documents, fraud, search

__all__ = ["auth_router", "documents", "fraud", "search"]
