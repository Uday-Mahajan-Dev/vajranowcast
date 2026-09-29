"""Database client initialization for Supabase."""

from supabase import Client, create_client
from app.config import settings


def get_supabase_client() -> Client:
    """Get standard Supabase client with anon key for public operations."""
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)


def get_supabase_admin() -> Client:
    """Get administrative Supabase client with service role key for backend operations."""
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
