"""JWT-based authentication for the IndyLeg API."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from config.settings import settings

# ── Constants ────────────────────────────────────────────────────────────────

_SECRET = settings.api_secret_key.get_secret_value()
_ALGORITHM = "HS256"
_ACCESS_TOKEN_EXPIRE_MINUTES = 60
_REFRESH_TOKEN_EXPIRE_DAYS = 7

_security = HTTPBearer()


# ── Roles ────────────────────────────────────────────────────────────────────


class Role(StrEnum):
    ADMIN = "admin"
    ATTORNEY = "attorney"
    CLERK = "clerk"
    VIEWER = "viewer"


# ── Schemas ──────────────────────────────────────────────────────────────────


class TokenPayload(BaseModel):
    sub: str  # username
    role: Role
    exp: datetime
    iat: datetime
    jti: str  # unique token id


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int  # seconds


class UserInfo(BaseModel):
    username: str
    role: Role


# ── Password hashing (HMAC-SHA256 with per-user salt) ────────────────────────


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Return (hashed, salt). Uses HMAC-SHA256 with a random 32-byte salt."""
    if salt is None:
        salt = secrets.token_hex(32)
    hashed = hmac.new(
        salt.encode(),
        password.encode(),
        hashlib.sha256,
    ).hexdigest()
    return hashed, salt


def verify_password(password: str, hashed: str, salt: str) -> bool:
    candidate, _ = hash_password(password, salt)
    return hmac.compare_digest(candidate, hashed)


# ── Token creation ───────────────────────────────────────────────────────────


def create_access_token(username: str, role: Role) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": username,
        "role": role.value,
        "iat": now,
        "exp": now + timedelta(minutes=_ACCESS_TOKEN_EXPIRE_MINUTES),
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)


def create_refresh_token(username: str) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": username,
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=_REFRESH_TOKEN_EXPIRE_DAYS),
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)


def create_token_pair(username: str, role: Role) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(username, role),
        refresh_token=create_refresh_token(username),
        expires_in=_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ── Token verification ──────────────────────────────────────────────────────


def decode_token(token: str) -> TokenPayload:
    try:
        data = jwt.decode(token, _SECRET, algorithms=[_ALGORITHM])
        return TokenPayload(
            sub=data["sub"],
            role=Role(data["role"]),
            exp=datetime.fromtimestamp(data["exp"], tz=timezone.utc),
            iat=datetime.fromtimestamp(data["iat"], tz=timezone.utc),
            jti=data["jti"],
        )
    except jwt.ExpiredSignatureError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        ) from err
    except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
        ) from exc


# ── FastAPI dependency ───────────────────────────────────────────────────────


async def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials, Depends(_security)],
) -> UserInfo:
    """Dependency — extracts and validates the current user from the Bearer token."""
    payload = decode_token(creds.credentials)
    return UserInfo(username=payload.sub, role=payload.role)


def require_role(*allowed: Role):
    """Factory for role-gating dependencies."""

    async def _check(user: Annotated[UserInfo, Depends(get_current_user)]) -> UserInfo:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' not authorized. Required: {[r.value for r in allowed]}",
            )
        return user

    return _check
