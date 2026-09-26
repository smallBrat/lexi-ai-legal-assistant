"""Singleton Supabase client for backend operations."""


from supabase import Client, create_client

from app.core.config import get_supabase_service_key, get_supabase_url

_supabase_client: Client | None = None


def get_supabase() -> Client:
    """Get the singleton Supabase client (backend use only - service role key).
    
    Returns:
        Supabase Client instance configured with service role key for backend operations.
    """
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = create_client(
            get_supabase_url(),
            get_supabase_service_key(),
        )
    return _supabase_client


def reset_supabase() -> None:
    """Reset the singleton Supabase client (useful for testing)."""
    global _supabase_client
    _supabase_client = None