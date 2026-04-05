"""Authentication endpoints — login, refresh, and user info."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.auth import (
    Role,
    TokenResponse,
    UserInfo,
    create_token_pair,
    decode_token,
    get_current_user,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# ── Seed users (replace with DB lookup in production) ────────────────────────

_SEED_SALT = "indyleg-dev-salt-do-not-use-in-production"

_USERS: dict[str, dict] = {
    "admin": {
        "hashed": hash_password("admin123", _SEED_SALT)[0],
        "salt": _SEED_SALT,
        "role": Role.ADMIN,
    },
    "attorney": {
        "hashed": hash_password("attorney123", _SEED_SALT)[0],
        "salt": _SEED_SALT,
        "role": Role.ATTORNEY,
    },
    "clerk": {
        "hashed": hash_password("clerk123", _SEED_SALT)[0],
        "salt": _SEED_SALT,
        "role": Role.CLERK,
    },
}


# ── Schemas ──────────────────────────────────────────────────────────────────


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=200)


class RefreshRequest(BaseModel):
    refresh_token: str


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/token", response_model=TokenResponse)
async def login(req: LoginRequest) -> TokenResponse:
    """Authenticate and return JWT access + refresh tokens."""
    user_record = _USERS.get(req.username)
    if not user_record or not verify_password(
        req.password, user_record["hashed"], user_record["salt"]
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    return create_token_pair(req.username, user_record["role"])


@router.post("/refresh", response_model=TokenResponse)
async def refresh(req: RefreshRequest) -> TokenResponse:
    """Exchange a refresh token for a new access + refresh token pair."""
    payload = decode_token(req.refresh_token)
    user_record = _USERS.get(payload.sub)
    if not user_record:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return create_token_pair(payload.sub, user_record["role"])


@router.get("/me", response_model=UserInfo)
async def me(user: UserInfo = Depends(get_current_user)) -> UserInfo:
    """Return the current authenticated user's info."""
    return user
