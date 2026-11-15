"""Supabase token verification and user synchronisation for OAuth sign-ins."""
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import HTTPException

from .config import SUPABASE_ANON_KEY, SUPABASE_URL


def fetch_supabase_user(access_token: str) -> dict:
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise HTTPException(503, "Supabase authentication is not configured on this server.")
    request = Request(
        f"{SUPABASE_URL}/auth/v1/user",
        headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {access_token}"},
    )
    try:
        with urlopen(request, timeout=8) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, json.JSONDecodeError):
        raise HTTPException(401, "Your Supabase session is invalid or has expired.")


def sync_google_user(conn, profile: dict) -> dict:
    email = (profile.get("email") or "").strip().lower()
    subject = profile.get("id")
    metadata = profile.get("user_metadata") or {}
    full_name = (metadata.get("full_name") or metadata.get("name") or email.split("@", 1)[0]).strip()
    if not email or not subject:
        raise HTTPException(422, "Google did not return a usable email address.")

    user = conn.execute(
        "SELECT id, email, full_name, role FROM users WHERE supabase_user_id = %s OR lower(email) = lower(%s)",
        (subject, email),
    ).fetchone()
    if user:
        user = conn.execute(
            """UPDATE users
               SET supabase_user_id = %s, full_name = %s, auth_provider = 'google'
               WHERE id = %s
               RETURNING id, email, full_name, role""",
            (subject, full_name, user["id"]),
        ).fetchone()
    else:
        user = conn.execute(
            """INSERT INTO users (supabase_user_id, email, password_hash, full_name, auth_provider)
               VALUES (%s, %s, %s, %s, 'google')
               RETURNING id, email, full_name, role""",
            (subject, email, "oauth-managed-by-supabase", full_name),
        ).fetchone()
    conn.commit()
    return user
