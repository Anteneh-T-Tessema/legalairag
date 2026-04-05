"""JWT-based authentication for the IndyLeg API."""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import threading
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

try:
    from enum import StrEnum
except ImportError:  # Python < 3.11
    from enum import Enum

    class StrEnum(str, Enum):  # type: ignore[no-redef]  # noqa: UP042
        pass


import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from config.settings import settings

logger = logging.getLogger(__name__)

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


# ── Token blacklist (revocation) ─────────────────────────────────────────────

_blacklist_lock = threading.Lock()
_blacklist: dict[str, float] = {}  # jti → expiry timestamp (UTC)

_BLACKLIST_MAX_SIZE = 10_000  # safety cap before forced prune


def _prune_blacklist() -> None:
    """Remove expired entries from the in-memory blacklist.  Caller must hold _blacklist_lock."""
    now = datetime.now(timezone.utc).timestamp()
    expired = [jti for jti, exp_ts in _blacklist.items() if exp_ts <= now]
    for jti in expired:
        del _blacklist[jti]


def _get_revocation_redis() -> Any:
    """Return a Redis client for token revocation, or None."""
    redis_url = getattr(settings, "redis_url", "")
    if not redis_url:
        return None
    try:
        import redis as _redis_lib

        r = _redis_lib.Redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=2)
        r.ping()
        return r
    except Exception:
        return None


def revoke_token(jti: str, expires_at: datetime) -> None:
    """Revoke a token by its JTI.  Uses Redis if available, else in-memory."""
    ttl = int((expires_at - datetime.now(timezone.utc)).total_seconds())
    if ttl <= 0:
        return  # already expired, nothing to revoke
    r = _get_revocation_redis()
    if r is not None:
        try:
            r.setex(f"revoked:{jti}", ttl, "1")
            return
        except Exception:
            logger.warning("Redis revocation failed, using in-memory fallback")
    with _blacklist_lock:
        if len(_blacklist) >= _BLACKLIST_MAX_SIZE:
            _prune_blacklist()
        _blacklist[jti] = expires_at.timestamp()


def is_token_revoked(jti: str) -> bool:
    """Check whether a JTI has been revoked."""
    r = _get_revocation_redis()
    if r is not None:
        try:
            return bool(r.exists(f"revoked:{jti}"))
        except Exception:  # noqa: S110 — intentional fallback to in-memory blacklist
            pass
    with _blacklist_lock:
        exp_ts = _blacklist.get(jti)
        if exp_ts is None:
            return False
        if exp_ts <= datetime.now(timezone.utc).timestamp():
            del _blacklist[jti]
            return False
        return True


# ── Schemas ──────────────────────────────────────────────────────────────────


class TokenPayload(BaseModel):
    sub: str  # username
    role: Role | None = None
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
        role_raw = data.get("role")
        payload = TokenPayload(
            sub=data["sub"],
            role=Role(role_raw) if role_raw else None,
            exp=datetime.fromtimestamp(data["exp"], tz=timezone.utc),
            iat=datetime.fromtimestamp(data["iat"], tz=timezone.utc),
            jti=data["jti"],
        )
        if is_token_revoked(payload.jti):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
            )
        return payload
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
    if payload.role is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing role")
    return UserInfo(username=payload.sub, role=payload.role)


def require_role(*allowed: Role) -> Callable[..., Awaitable[UserInfo]]:
    """Factory for role-gating dependencies."""

    async def _check(user: Annotated[UserInfo, Depends(get_current_user)]) -> UserInfo:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' not authorized. Required: {[r.value for r in allowed]}",
            )
        return user

    return _check
