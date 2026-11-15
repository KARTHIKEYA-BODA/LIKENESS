from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..db import get_conn
from ..security import current_user, hash_password, make_token, verify_password
from ..supabase_auth import fetch_supabase_user, sync_google_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterIn(BaseModel):
    email: str = Field(min_length=5, max_length=200)
    password: str = Field(min_length=6, max_length=100)
    full_name: str = Field(min_length=1, max_length=100)


class LoginIn(BaseModel):
    email: str
    password: str


class SupabaseTokenIn(BaseModel):
    access_token: str = Field(min_length=20)


@router.post("/supabase")
def supabase_login(body: SupabaseTokenIn, conn=Depends(get_conn)):
    """Exchange a verified Supabase Google session for this API's JWT."""
    profile = fetch_supabase_user(body.access_token)
    if profile.get("app_metadata", {}).get("provider") != "google":
        raise HTTPException(403, "Please sign in with Google.")
    user = sync_google_user(conn, profile)
    return {"token": make_token(user), "user": user}


@router.post("/register")
def register(body: RegisterIn, conn=Depends(get_conn)):
    if "@" not in body.email:
        raise HTTPException(422, "Enter a valid email address.")
    exists = conn.execute("SELECT 1 FROM users WHERE lower(email) = lower(%s)", (body.email,)).fetchone()
    if exists:
        raise HTTPException(409, "An account with this email already exists.")
    user = conn.execute(
        """INSERT INTO users (email, password_hash, full_name) VALUES (%s, %s, %s)
           RETURNING id, email, full_name, role""",
        (body.email.strip(), hash_password(body.password), body.full_name.strip()),
    ).fetchone()
    conn.commit()
    return {"token": make_token(user), "user": user}


@router.post("/login")
def login(body: LoginIn, conn=Depends(get_conn)):
    row = conn.execute("SELECT * FROM users WHERE lower(email) = lower(%s)", (body.email,)).fetchone()
    if not row or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(401, "Email or password is incorrect.")
    user = {k: row[k] for k in ("id", "email", "full_name", "role")}
    return {"token": make_token(user), "user": user}


@router.get("/me")
def me(user=Depends(current_user)):
    return user
