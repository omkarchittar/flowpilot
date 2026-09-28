"""Opaque sessions, browser CSRF protection and persisted login throttles."""

import hashlib
import hmac
import secrets
from collections.abc import Iterator
from datetime import timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator
from sqlalchemy import case, delete, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from flowpilot.db import utcnow
from flowpilot.models import AuthSession, LoginThrottle, User
from flowpilot.security import hash_password, session_digest, verify_password

router = APIRouter(prefix="/api", tags=["identity"])
COOKIE = "flowpilot_session"
# Equal-cost password verification even for nonexistent accounts.
DUMMY_HASH = hash_password(secrets.token_urlsafe(32))


def get_db(request: Request) -> Iterator[Session]:
    with request.app.state.database.sessions() as db:
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise


Db = Annotated[Session, Depends(get_db, scope="function")]


def bearer_or_cookie(request: Request) -> tuple[str, bool]:
    authorization = request.headers.get("Authorization")
    if authorization is not None:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(401, "Authentication required")
        return token, False
    return request.cookies.get(COOKIE, ""), True


def csrf_token(token: str) -> str:
    return hmac.new(token.encode(), b"flowpilot-csrf-v1", hashlib.sha256).hexdigest()


def current_user(request: Request, db: Db) -> User:
    token, cookie_auth = bearer_or_cookie(request)
    if not 40 <= len(token) <= 128:
        raise HTTPException(401, "Authentication required")
    user = db.scalar(
        select(User)
        .join(AuthSession, AuthSession.user_id == User.id)
        .where(
            AuthSession.token_hash == session_digest(token),
            AuthSession.expires_at > utcnow(),
            User.active.is_(True),
        )
        .execution_options(populate_existing=True)
    )
    if user is None:
        raise HTTPException(401, "Authentication required")
    if cookie_auth and request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("Origin")
        supplied = request.headers.get("X-CSRF-Token", "")
        if origin not in request.app.state.settings.allowed_origins or not hmac.compare_digest(
            supplied.encode(), csrf_token(token).encode()
        ):
            raise HTTPException(403, "Browser request could not be verified")
    return user


Actor = Annotated[User, Depends(current_user)]


def public_user(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "active": user.active,
        "created_at": user.created_at,
    }


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Credentials(Input):
    email: EmailStr
    password: SecretStr = Field(min_length=1, max_length=1024)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        return value.casefold()


class UserCreate(Credentials):
    password: SecretStr = Field(min_length=12, max_length=1024)
    name: str = Field(min_length=1, max_length=200)
    role: Literal["requester", "reviewer", "approver", "admin"] = "requester"


class UserUpdate(Input):
    active: bool | None = None
    role: Literal["requester", "reviewer", "approver", "admin"] | None = None


def consume_login_budget(db: Session, *, email: str, address: str) -> bool:
    """Atomic upsert counters; commits before credential validation, including failures."""
    now = utcnow()
    cutoff = now - timedelta(minutes=15)
    allowed = True
    for subject, maximum in [("ip:" + address, 50), ("account:" + email, 10)]:
        key = hashlib.sha256(subject.encode()).hexdigest()
        statement = insert(LoginThrottle).values(subject_hash=key, attempts=1, window_start=now)
        count = db.scalar(
            statement.on_conflict_do_update(
                index_elements=["subject_hash"],
                set_={
                    "attempts": case(
                        (LoginThrottle.window_start <= cutoff, 1), else_=LoginThrottle.attempts + 1
                    ),
                    "window_start": case(
                        (LoginThrottle.window_start <= cutoff, now),
                        else_=LoginThrottle.window_start,
                    ),
                },
            ).returning(LoginThrottle.attempts)
        )
        if count > maximum:
            allowed = False
            break
    db.execute(delete(LoginThrottle).where(LoginThrottle.window_start < now - timedelta(days=1)))
    db.commit()
    return allowed


def authenticate(request: Request, db: Session, credentials: Credentials) -> tuple[User, str]:
    origin = request.headers.get("Origin")
    if origin is not None and origin not in request.app.state.settings.allowed_origins:
        raise HTTPException(403, "Browser origin is not allowed")
    address = request.client.host if request.client else "unknown"
    if not consume_login_budget(db, email=str(credentials.email), address=address):
        raise HTTPException(
            429, "Too many login attempts; retry after the current 15-minute window"
        )
    user = db.scalar(select(User).where(User.email == str(credentials.email)))
    valid = verify_password(
        credentials.password.get_secret_value(), user.password_hash if user else DUMMY_HASH
    )
    if not valid or user is None or not user.active:
        raise HTTPException(401, "Email or password is incorrect")
    token = secrets.token_urlsafe(32)
    db.execute(delete(AuthSession).where(AuthSession.expires_at <= utcnow()))
    db.add(
        AuthSession(
            token_hash=session_digest(token),
            user_id=user.id,
            expires_at=utcnow() + timedelta(hours=request.app.state.settings.session_hours),
        )
    )
    db.flush()
    return user, token


@router.post("/auth/login")
def login(credentials: Credentials, request: Request, response: Response, db: Db):
    user, token = authenticate(request, db, credentials)
    settings = request.app.state.settings
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        secure=settings.environment == "production",
        samesite="strict",
        max_age=settings.session_hours * 3600,
        path="/",
    )
    return {"user": public_user(user), "csrf_token": csrf_token(token)}


@router.post("/auth/token")
def issue_token(credentials: Credentials, request: Request, db: Db):
    user, token = authenticate(request, db, credentials)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": request.app.state.settings.session_hours * 3600,
        "user": public_user(user),
    }


@router.get("/auth/me")
def me(request: Request, actor: Actor):
    token, cookie_auth = bearer_or_cookie(request)
    return {"user": public_user(actor), "csrf_token": csrf_token(token) if cookie_auth else None}


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, db: Db, actor: Actor):
    token, _ = bearer_or_cookie(request)
    db.execute(delete(AuthSession).where(AuthSession.token_hash == session_digest(token)))
    response.delete_cookie(COOKIE, path="/")


def require_admin(db: Session, actor: User) -> User:
    # Consistent lock order for account provisioning/revocation and last-admin checks.
    db.execute(text("SELECT pg_advisory_xact_lock(90421871)"))
    actor = db.scalar(
        select(User)
        .where(User.id == actor.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if actor is None or not actor.active or actor.role != "admin":
        raise HTTPException(403, "Administrator role required")
    return actor


@router.get("/admin/users")
def list_users(db: Db, actor: Actor):
    require_admin(db, actor)
    return [
        public_user(user) for user in db.scalars(select(User).order_by(User.created_at).limit(200))
    ]


@router.post("/admin/users", status_code=201)
def create_user(body: UserCreate, db: Db, actor: Actor):
    require_admin(db, actor)
    row = User(
        email=str(body.email),
        name=body.name,
        role=body.role,
        password_hash=hash_password(body.password.get_secret_value()),
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError as exc:
        raise HTTPException(409, "An account with that email already exists") from exc
    return public_user(row)


@router.patch("/admin/users/{user_id}")
def update_user(user_id: str, body: UserUpdate, db: Db, actor: Actor):
    require_admin(db, actor)
    target = db.scalar(
        select(User)
        .where(User.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if target is None:
        raise HTTPException(404, "User not found")
    if (
        target.active
        and target.role == "admin"
        and (body.active is False or body.role not in {None, "admin"})
    ):
        count = db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.active.is_(True), User.role == "admin")
        )
        if count <= 1:
            raise HTTPException(409, "At least one active administrator is required")
    if body.active is not None:
        target.active = body.active
    if body.role is not None:
        target.role = body.role
    db.execute(delete(AuthSession).where(AuthSession.user_id == target.id))
    db.flush()
    return public_user(target)
