import logging
import subprocess
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

_TELEGRAM_SCRIPT = "/home/measly/.claude/scripts/telegram-send.sh"
_KST = timedelta(hours=9)

_PROVIDER_LABEL = {
    "google": "Google",
    "lnauth": "Lightning",
    "email": "이메일",
}


def _now_kst() -> str:
    return (datetime.now(timezone.utc) + _KST).strftime("%Y-%m-%d %H:%M")


def _send(msg: str) -> None:
    try:
        subprocess.run(
            ["bash", _TELEGRAM_SCRIPT, msg],
            timeout=10,
            capture_output=True,
        )
    except Exception as e:
        logger.warning("텔레그램 전송 실패 (무시): %s", e)


def notify_new_user(username: str, email: str | None, provider: str) -> None:
    label = _PROVIDER_LABEL.get(provider, provider)
    email_line = f"• 이메일: {email}\n" if email else ""
    _send(
        f"[Event] 👤 <b>신규 가입</b>\n"
        f"• 닉네임: {username}\n"
        f"{email_line}"
        f"• 가입 방식: {label}\n"
        f"🕐 {_now_kst()}"
    )


def notify_backend_error(error: Exception, context: str = "") -> None:
    error_msg = str(error)
    if len(error_msg) > 400:
        error_msg = error_msg[:400] + "…"
    ctx_line = f"• 컨텍스트: {context}\n" if context else ""
    _send(
        f"[Event] ❌ <b>백엔드 에러</b>\n"
        f"{ctx_line}"
        f"• 오류: <code>{type(error).__name__}: {error_msg}</code>\n"
        f"🕐 {_now_kst()}"
    )
