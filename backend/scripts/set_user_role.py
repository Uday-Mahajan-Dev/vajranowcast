"""
Script to set user roles in Supabase Auth using the Service Role Key.
Usage:
    python scripts/set_user_role.py <USER_EMAIL_OR_UUID> <ROLE: meteorologist|admin|viewer>
"""

import sys
import os
from supabase import create_client

# Add parent directory to sys.path to load settings
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import settings


def set_role(user_identifier: str, role: str):
    if role not in ["admin", "meteorologist", "viewer"]:
        print(f"Error: Invalid role '{role}'. Allowed roles: admin, meteorologist, viewer")
        sys.exit(1)

    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
        print("Error: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env")
        sys.exit(1)

    supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

    print(f"Connecting to Supabase project {settings.SUPABASE_URL}...")
    admin_auth = supabase.auth.admin

    # Search for user if email provided
    target_id = user_identifier
    if "@" in user_identifier:
        print(f"Finding user with email {user_identifier}...")
        users = admin_auth.list_users()
        found = False
        for u in users:
            if u.email.lower() == user_identifier.lower():
                target_id = u.id
                found = True
                break
        if not found:
            print(f"User with email '{user_identifier}' not found in Supabase Auth.")
            sys.exit(1)

    print(f"Updating app_metadata for user ID: {target_id} with role '{role}'...")
    res = admin_auth.update_user_by_id(
        target_id,
        {"app_metadata": {"role": role}}
    )
    print(f"Success! User {res.user.email} (ID: {res.user.id}) now has role: {res.user.app_metadata.get('role')}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python scripts/set_user_role.py <email_or_user_id> <role>")
        sys.exit(1)

    set_role(sys.argv[1], sys.argv[2])
