from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import JWT_HOURS, JWT_SECRET
from .db import get_conn

bearer = HTTPBearer(auto_error=False)


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def make_token(user: dict) -> str:
    payload = {
        "sub": str(user["id"]),
        "role": user["role"],
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def _load_user(creds: HTTPAuthorizationCredentials | None, conn):
    if not creds:
        return None
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=["HS256"])
        uid = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
    return conn.execute(
        "SELECT id, email, full_name, role FROM users WHERE id = %s", (uid,)
    ).fetchone()


def current_user(creds=Depends(bearer), conn=Depends(get_conn)) -> dict:
    user = _load_user(creds, conn)
    if not user:
        raise HTTPException(401, "Please sign in to continue.")
    return user


def optional_user(creds=Depends(bearer), conn=Depends(get_conn)) -> dict | None:
    return _load_user(creds, conn)


def require_admin(user=Depends(current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(403, "Admin access required.")
    return user
