import html
import json
import logging
import re
from datetime import datetime
from pathlib import Path

from contextlib import asynccontextmanager

import anyio
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.models.post import Post
from app.routes import admin, auth, challenges, comments, feed, history, notifications, survey, users, videos
from app.services.r2 import ensure_r2_cors
from app.services.notify import notify_backend_error

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _validation_field_name(loc: tuple | list | None) -> str:
    field = loc[-1] if loc else None
    return {
        "email": "이메일",
        "username": "닉네임",
        "password": "비밀번호",
        "lightning_address": "라이트닝 주소",
        "caption": "내용",
        "title": "제목",
    }.get(field, "입력값")


def _validation_error_message(errors: list[dict]) -> str:
    if not errors:
        return "입력값을 다시 확인해주세요."
    first = errors[0]
    loc = first.get("loc")
    error_type = str(first.get("type", ""))
    msg = str(first.get("msg", ""))
    name = _validation_field_name(loc if isinstance(loc, (list, tuple)) else None)

    if name == "비밀번호" and ("string_too_short" in error_type or "at least 8" in msg or "min_length" in msg):
        return "비밀번호는 8자 이상 입력해주세요."
    if name == "비밀번호" and ("string_too_long" in error_type or "at most 100" in msg or "max_length" in msg):
        return "비밀번호는 100자 이하로 입력해주세요."
    if name == "닉네임" and ("string_too_short" in error_type or "at least 2" in msg or "min_length" in msg):
        return "닉네임은 2자 이상 입력해주세요."
    if name == "닉네임" and ("string_too_long" in error_type or "at most 30" in msg or "max_length" in msg):
        return "닉네임은 30자 이하로 입력해주세요."
    if name == "이메일" or "email" in msg.lower():
        return "이메일 형식이 올바르지 않습니다."
    if "missing" in error_type:
        return f"{name}을(를) 입력해주세요."
    if "string_too_short" in error_type:
        return f"{name}이(가) 너무 짧습니다."
    if "string_too_long" in error_type:
        return f"{name}이(가) 너무 깁니다."
    return f"{name}을(를) 다시 확인해주세요."

@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    await anyio.to_thread.run_sync(ensure_r2_cors)
    yield


app = FastAPI(title="Stack Health", version="0.1.0", lifespan=lifespan)
app.router.redirect_slashes = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    logger.warning("Validation error: %s %s — %s", request.method, request.url.path, errors)
    message = _validation_error_message(errors)
    return JSONResponse(
        status_code=422,
        content={"detail": message, "message": message},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled exception: %s %s — %s", request.method, request.url.path, exc, exc_info=True)
    notify_backend_error(exc, f"{request.method} {request.url.path}")
    return JSONResponse(
        status_code=500,
        content={"detail": "서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요"},
    )


@app.middleware("http")
async def add_security_headers(request: Request, call_next) -> Response:
    response = await call_next(request)
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Embedder-Policy"] = "credentialless"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(self), geolocation=(), payment=()"
    return response


app.include_router(auth.router)
app.include_router(videos.router)
app.include_router(feed.router)
app.include_router(admin.router)
app.include_router(comments.router)
app.include_router(history.router)
app.include_router(challenges.router)
app.include_router(users.router)
app.include_router(notifications.router)
app.include_router(survey.router)


@app.get("/health")
def health() -> dict:
    try:
        version = Path(__file__).parent.parent.parent.joinpath("VERSION").read_text().strip()
    except FileNotFoundError:
        version = "unknown"
    return {"status": "ok", "version": version}


_CRAWLER_RE = re.compile(
    r"(Twitterbot|facebookexternalhit|LinkedInBot|TelegramBot|Slackbot|"
    r"WhatsApp|kakaotalk-scrap|KakaoTalk|Discordbot|Googlebot|bingbot|"
    r"ia_archiver|Applebot|vk\.com/dev/Share)",
    re.IGNORECASE,
)

_SHORTS_RE = re.compile(r"^shorts/([A-Za-z0-9_-]+)$")


def _is_crawler(request: Request) -> bool:
    ua = request.headers.get("user-agent", "")
    return bool(_CRAWLER_RE.search(ua))


def _build_og_meta(post: "Post") -> tuple[str, str]:  # type: ignore[name-defined]
    """Return (og_title, og_description) with meaningful content."""
    username = post.user.username if post.user else "운동러"

    # Title: "{caption} — @{username}" or fallback
    if post.caption and post.caption.strip():
        title = f"{post.caption.strip()} — @{username}"
    else:
        title = f"@{username}의 운동 기록"

    # Description parts
    parts: list[str] = []

    # Tags as hashtags
    try:
        tags: list[str] = json.loads(post.tags) if post.tags else []
    except (json.JSONDecodeError, TypeError):
        tags = []
    if tags:
        parts.append(" ".join(f"#{t}" for t in tags[:5]))

    # Workout duration
    if post.workout_start and post.workout_end:
        try:
            fmt = "%H:%M"
            start = datetime.strptime(post.workout_start, fmt)
            end = datetime.strptime(post.workout_end, fmt)
            minutes = int((end - start).total_seconds() / 60)
            if minutes > 0:
                parts.append(f"{minutes}분 운동")
        except ValueError:
            pass

    parts.append("Stack Health")
    description = " · ".join(parts)
    return title, description


def _og_html(title: str, description: str, image: str, url: str, video_url: str | None) -> str:
    t = html.escape(title)
    d = html.escape(description)
    i = html.escape(image)
    u = html.escape(url)
    video_tags = (
        f'<meta property="og:video" content="{html.escape(video_url)}" />'
        f'<meta property="og:video:type" content="video/mp4" />'
        if video_url
        else ""
    )
    return f"""<!doctype html>
<html>
<head>
<meta charset="UTF-8" />
<title>{t}</title>
<meta property="og:type" content="video.other" />
<meta property="og:site_name" content="Stack Health" />
<meta property="og:title" content="{t}" />
<meta property="og:description" content="{d}" />
<meta property="og:image" content="{i}" />
<meta property="og:image:width" content="1080" />
<meta property="og:image:height" content="1920" />
<meta property="og:url" content="{u}" />
{video_tags}
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content="{t}" />
<meta name="twitter:description" content="{d}" />
<meta name="twitter:image" content="{i}" />
</head>
<body><script>window.location.href="{u}";</script></body>
</html>"""


# Serve React SPA (production: static/ dir built by Docker)
_static_dir = Path(__file__).parent.parent / "static"
if _static_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(_static_dir / "assets")), name="assets")

    @app.head("/", include_in_schema=False)
    @app.head("/{full_path:path}", include_in_schema=False)
    def spa_fallback_head() -> Response:
        return Response(status_code=200)

    @app.get("/{full_path:path}", response_model=None)
    def spa_fallback(
        full_path: str,
        request: Request,
    ) -> FileResponse | HTMLResponse:
        # Serve static files first
        file_path = _static_dir / full_path
        if file_path.exists() and file_path.is_file():
            name = file_path.name
            if name == "sw.js" or name.startswith("workbox-"):
                return FileResponse(
                    str(file_path),
                    headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
                )
            return FileResponse(str(file_path))

        # OG tag injection for share pages (crawler only) — DB session opened only here
        m = _SHORTS_RE.match(full_path)
        if m and _is_crawler(request):
            share_token = m.group(1)
            from sqlalchemy.orm import selectinload as _sil
            from app.database import SessionLocal
            db = SessionLocal()
            try:
                post = (
                    db.query(Post)
                    .options(_sil(Post.user), _sil(Post.video))
                    .filter(Post.share_token == share_token)
                    .first()
                )
                if post:
                    from app.config import settings as app_settings
                    base = app_settings.app_base_url.rstrip("/")
                    image = post.thumbnail_url or f"{base}/og-image.png"
                    video_url = post.video.cdn_url if post.video else None
                    page_url = f"{base}/shorts/{share_token}"
                    og_title, og_desc = _build_og_meta(post)
                    return HTMLResponse(
                        content=_og_html(og_title, og_desc, image, page_url, video_url),
                        headers={"Cache-Control": "public, max-age=3600"},
                    )
            finally:
                db.close()

        return FileResponse(
            str(_static_dir / "index.html"),
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
