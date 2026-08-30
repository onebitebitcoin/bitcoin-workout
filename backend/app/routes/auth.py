import asyncio
import io
import random
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.lnauth_challenge import LNAuthChallenge
from app.models.user import User
from app.schemas.user import (
    LoginRequest,
    RefreshRequest,
    RefreshResponse,
    RegisterRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserSchema,
)
from app.services.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_user_by_email,
    get_user_by_id,
    hash_password,
    verify_password,
)
from app.services import r2 as r2_service
from app.services.google_oauth import exchange_code, generate_oauth_state, get_google_auth_url, get_google_user_info, verify_oauth_state
from app.services.lnauth import encode_lnurl, generate_k1, verify_signature
from app.services.rate_limit import check_rate_limit
from app.services.notify import notify_new_user
from app.services.referral import generate_referral_code
from app.services.error_codes import (
    api_error,
    E_AUTH_EMAIL_TAKEN,
    E_AUTH_INVALID_CREDENTIALS,
    E_AUTH_INVALID_TOKEN,
    E_AUTH_REQUIRED,
    E_AUTH_USERNAME_TAKEN,
    E_BANNED,
    E_CHALLENGE_EXPIRED,
    E_CHALLENGE_INVALID,
    E_FILE_TOO_LARGE,
    E_GOOGLE_AUTH_UNAVAILABLE,
    E_IMAGE_FORMAT_INVALID,
    E_USER_NOT_FOUND,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

LNAUTH_CHALLENGE_TTL = timedelta(minutes=10)


def _as_utc(dt: datetime) -> datetime:
    """Return dt as UTC-aware. SQLite returns naive; Postgres returns aware."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

PROFILE_COLORS = [
    "#6366f1", "#8b5cf6", "#ec4899", "#f97316",
    "#14b8a6", "#22c55e", "#3b82f6", "#eab308",
]
AVATAR_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
AVATAR_CONTENT_TYPE_TO_EXT: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}
AVATAR_MAX_SIZE = 5 * 1024 * 1024  # 5MB


def _random_profile_color() -> str:
    return random.choice(PROFILE_COLORS)
class _BearerAuth(HTTPBearer):
    async def __call__(self, request: Request) -> HTTPAuthorizationCredentials:
        try:
            return await super().__call__(request)
        except HTTPException:
            raise api_error(status.HTTP_401_UNAUTHORIZED, E_AUTH_REQUIRED, "인증이 필요합니다")


bearer = _BearerAuth()
bearer_optional = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    user_id = decode_token(credentials.credentials)
    if user_id is None:
        raise api_error(status.HTTP_401_UNAUTHORIZED, E_AUTH_INVALID_TOKEN, "유효하지 않은 토큰입니다")
    user = get_user_by_id(db, user_id)
    if user is None:
        raise api_error(status.HTTP_401_UNAUTHORIZED, E_USER_NOT_FOUND, "사용자를 찾을 수 없습니다")
    return user


def get_active_user(user: User = Depends(get_current_user)) -> User:
    """get_current_user + ban check. Use on write/action endpoints."""
    if user.is_banned:
        raise api_error(403, E_BANNED, "계정이 정지된 상태입니다")
    return user


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_optional),
    db: Session = Depends(get_db),
) -> User | None:
    if not credentials:
        return None
    user_id = decode_token(credentials.credentials)
    if user_id is None:
        return None
    return get_user_by_id(db, user_id)


@router.post("/register")
async def register(req: RegisterRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    check_rate_limit(request, "auth:register", max_calls=5, period_seconds=3600)
    if get_user_by_email(db, req.email):
        raise api_error(400, E_AUTH_EMAIL_TAKEN, "이미 사용 중인 이메일입니다")
    if db.query(User).filter(User.username == req.username).first():
        raise api_error(400, E_AUTH_USERNAME_TAKEN, "이미 사용 중인 닉네임입니다")

    loop = asyncio.get_running_loop()
    password_hash = await loop.run_in_executor(None, hash_password, req.password)

    # 초대 코드: 유효하면 referred_by 기록 (보상 없음, 신규 가입에만 적용)
    referred_by_id: int | None = None
    if req.referral_code:
        inviter = db.query(User).filter(User.referral_code == req.referral_code.strip()).first()
        if inviter:
            referred_by_id = inviter.id

    user = User(
        email=req.email,
        username=req.username,
        password_hash=password_hash,
        app_settings={"profile_color": _random_profile_color()},
        referral_code=generate_referral_code(db),
        referred_by_id=referred_by_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id)
    refresh = create_refresh_token(user.id)
    notify_new_user(user.username, user.email, "email")
    return {"data": TokenResponse(access_token=token, refresh_token=refresh, user=UserSchema.model_validate(user))}


_DUMMY_HASH = "$2b$10$bUTcbia9bmP44rUY1VwI6ug8a0fR68wtSzXIBzHxCsfh5DiI54e4e"


@router.post("/login")
async def login(req: LoginRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    check_rate_limit(request, "auth:login", max_calls=10, period_seconds=900)
    user = get_user_by_email(db, req.email)
    # user가 없어도 항상 bcrypt 실행 — 응답 시간으로 이메일 존재 여부 추론 방지
    hash_to_check = user.password_hash if user is not None else _DUMMY_HASH
    loop = asyncio.get_running_loop()
    ok = await loop.run_in_executor(None, verify_password, req.password, hash_to_check)
    if not ok or user is None:
        raise api_error(401, E_AUTH_INVALID_CREDENTIALS, "이메일 또는 비밀번호가 올바르지 않습니다")

    token = create_access_token(user.id)
    refresh = create_refresh_token(user.id)
    return {"data": TokenResponse(access_token=token, refresh_token=refresh, user=UserSchema.model_validate(user))}


@router.post("/refresh")
def refresh_token(req: RefreshRequest, db: Session = Depends(get_db)) -> dict:
    user_id = decode_token(req.refresh_token, expected_type="refresh")
    if user_id is None:
        raise api_error(status.HTTP_401_UNAUTHORIZED, E_AUTH_INVALID_TOKEN, "유효하지 않은 토큰입니다")
    user = get_user_by_id(db, user_id)
    if user is None:
        raise api_error(status.HTTP_401_UNAUTHORIZED, E_USER_NOT_FOUND, "사용자를 찾을 수 없습니다")
    # sliding window: 갱신할 때마다 refresh도 새로 발급해 만료 연장
    return {
        "data": RefreshResponse(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
        )
    }


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)) -> dict:
    return {"data": UserSchema.model_validate(current_user)}


@router.get("/check-username")
def check_username(
    username: str,
    token: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    if len(username) < 2 or len(username) > 30:
        return {"data": {"available": False}}
    exclude_id: int | None = None
    if token:
        try:
            from app.services.auth import decode_token
            exclude_id = decode_token(token)
        except Exception:
            pass
    query = db.query(User).filter(User.username == username)
    if exclude_id:
        query = query.filter(User.id != exclude_id)
    return {"data": {"available": query.first() is None}}


@router.patch("/me")
def update_me(
    req: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if req.username is not None:
        existing = db.query(User).filter(
            User.username == req.username, User.id != current_user.id
        ).first()
        if existing:
            raise api_error(400, E_AUTH_USERNAME_TAKEN, "이미 사용 중인 닉네임입니다")
        current_user.username = req.username
        settings = dict(current_user.app_settings or {})
        settings.pop("needs_username", None)
        current_user.app_settings = settings
    if req.lightning_address is not None:
        current_user.lightning_address = req.lightning_address
    if req.app_settings is not None:
        current_user.app_settings = req.app_settings

    db.commit()
    db.refresh(current_user)
    return {"data": UserSchema.model_validate(current_user)}


@router.post("/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    content_type = file.content_type or ""
    if content_type not in AVATAR_ALLOWED_TYPES:
        raise api_error(400, E_IMAGE_FORMAT_INVALID, "이미지 파일(jpeg/png/webp/gif)만 업로드할 수 있습니다")

    data = await file.read()
    if len(data) > AVATAR_MAX_SIZE:
        raise api_error(400, E_FILE_TOO_LARGE, "파일 크기는 5MB 이하여야 합니다")

    ext = AVATAR_CONTENT_TYPE_TO_EXT[content_type]
    r2_key = f"avatars/{uuid.uuid4()}.{ext}"
    client = r2_service.get_r2_client()
    client.upload_fileobj(
        io.BytesIO(data),
        settings.r2_bucket_name,
        r2_key,
        ExtraArgs={"ContentType": content_type},
    )
    avatar_url = r2_service.get_cdn_url(r2_key)
    current_user.avatar_url = avatar_url
    db.commit()
    db.refresh(current_user)
    return {"data": UserSchema.model_validate(current_user)}


# ── Google OAuth ──────────────────────────────────────────────────────

@router.get("/google")
def google_login() -> RedirectResponse:
    if not settings.google_client_id:
        raise api_error(503, E_GOOGLE_AUTH_UNAVAILABLE, "Google 로그인을 현재 사용할 수 없습니다")
    state = generate_oauth_state()
    url = get_google_auth_url(state=state)
    return RedirectResponse(url=url)


@router.get("/google/callback")
async def google_callback(code: str | None = None, error: str | None = None, state: str | None = None, db: Session = Depends(get_db)) -> RedirectResponse:
    if error or not code:
        return RedirectResponse(url=f"{settings.app_base_url}/?error=google_auth_failed")
    if not verify_oauth_state(state):
        return RedirectResponse(url=f"{settings.app_base_url}/?error=google_auth_failed")
    try:
        tokens = await exchange_code(code)
        user_info = await get_google_user_info(tokens["access_token"])
    except Exception:
        return RedirectResponse(url=f"{settings.app_base_url}/?error=google_auth_failed")

    google_sub = user_info.get("sub")
    email = user_info.get("email")
    name = user_info.get("name") or user_info.get("given_name") or "user"
    avatar = user_info.get("picture")

    email_verified = user_info.get("email_verified", False)
    user = db.query(User).filter(User.oauth_sub == google_sub, User.oauth_provider == "google").first()
    if user is None and email and email_verified:
        user = db.query(User).filter(User.email == email).first()

    is_new = user is None
    if user is None:
        base_username = name.lower().replace(" ", "_")[:20]
        username = base_username
        suffix = 1
        while db.query(User).filter(User.username == username).first():
            username = f"{base_username}_{suffix}"
            suffix += 1
        user = User(
            email=email,
            username=username,
            password_hash=None,
            oauth_provider="google",
            oauth_sub=google_sub,
            avatar_url=avatar,
            app_settings={"needs_username": True, "profile_color": _random_profile_color()},
            referral_code=generate_referral_code(db),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        notify_new_user(user.username, user.email, "google")
    else:
        if not user.oauth_sub:
            user.oauth_sub = google_sub
            user.oauth_provider = "google"
        if avatar and not user.avatar_url:
            user.avatar_url = avatar
        db.commit()

    token = create_access_token(user.id)
    refresh = create_refresh_token(user.id)
    # Use fragment (#) instead of query string to keep JWT out of server logs and referrer headers
    new_param = "&new_user=1" if is_new else ""
    redirect_url = f"{settings.app_base_url}/#google_token={token}&google_refresh={refresh}{new_param}"
    return RedirectResponse(url=redirect_url)


# ── LNAuth ────────────────────────────────────────────────────────────

@router.get("/lnauth/challenge")
def lnauth_challenge(db: Session = Depends(get_db)) -> dict:
    # Cleanup stale challenges (older than 30 minutes)
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
    db.query(LNAuthChallenge).filter(LNAuthChallenge.created_at < cutoff).delete()

    k1 = generate_k1()
    lnurl = encode_lnurl(k1)
    challenge = LNAuthChallenge(k1=k1)
    db.add(challenge)
    db.commit()
    return {"data": {"k1": k1, "lnurl": lnurl}}


@router.get("/lnauth")
def lnauth_callback(
    tag: str,
    k1: str,
    sig: str | None = None,
    key: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    challenge = db.query(LNAuthChallenge).filter(LNAuthChallenge.k1 == k1).first()
    if not challenge:
        raise api_error(400, E_CHALLENGE_INVALID, "유효하지 않은 챌린지입니다")
    if datetime.now(timezone.utc) - _as_utc(challenge.created_at) > LNAUTH_CHALLENGE_TTL:
        db.delete(challenge)
        db.commit()
        raise api_error(400, E_CHALLENGE_EXPIRED, "챌린지가 만료되었습니다. 다시 시도해주세요")

    if sig is None or key is None:
        return {
            "tag": "login",
            "k1": k1,
            "action": "login",
            "callback": f"{settings.lnurl_origin}/api/v1/auth/lnauth",
        }

    if not verify_signature(k1, sig, key):
        return {"status": "ERROR", "reason": "서명이 유효하지 않습니다"}

    user = db.query(User).filter(User.oauth_sub == key, User.oauth_provider == "lnauth").first()
    if user is None:
        base_username = f"ln_{key[:12]}"
        username = base_username
        suffix = 1
        while db.query(User).filter(User.username == username).first():
            username = f"{base_username}_{suffix}"
            suffix += 1
        user = User(
            email=None,
            username=username,
            password_hash=None,
            oauth_provider="lnauth",
            oauth_sub=key,
            app_settings={"needs_username": True, "profile_color": _random_profile_color()},
            referral_code=generate_referral_code(db),
        )
        db.add(user)
        db.flush()
        notify_new_user(user.username, None, "lnauth")

    challenge.pubkey = key
    challenge.verified = True
    db.commit()

    return {"status": "OK"}


@router.get("/lnauth/verify")
def lnauth_verify(k1: str, db: Session = Depends(get_db)) -> dict:
    challenge = db.query(LNAuthChallenge).filter(LNAuthChallenge.k1 == k1).first()
    if not challenge or not challenge.verified:
        return {"data": {"verified": False}}
    if datetime.now(timezone.utc) - _as_utc(challenge.created_at) > LNAUTH_CHALLENGE_TTL:
        db.delete(challenge)
        db.commit()
        return {"data": {"verified": False}}

    user = db.query(User).filter(
        User.oauth_sub == challenge.pubkey,
        User.oauth_provider == "lnauth",
    ).first()
    if not user:
        return {"data": {"verified": False}}

    is_new_user = bool((user.app_settings or {}).get("needs_username", False))
    token = create_access_token(user.id)
    refresh = create_refresh_token(user.id)
    return {"data": {"verified": True, "token": token, "refresh_token": refresh, "is_new_user": is_new_user}}
