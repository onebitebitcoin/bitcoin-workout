"""날짜 경계 계산 유틸.

서비스의 집계 기준은 국가별 로컬 자정이 아니라 글로벌 UTC 캘린더다 (SPEC.md 2장).
클라이언트 타임존은 사용자에게 날짜를 보여주거나 캘린더를 그릴 때만 넘긴다.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC = ZoneInfo("UTC")


def parse_tz(tz_str: str) -> ZoneInfo:
    """X-Client-Timezone 헤더 값을 ZoneInfo로. 알 수 없는 값은 UTC로 떨어뜨린다."""
    try:
        return ZoneInfo(tz_str)
    except (ZoneInfoNotFoundError, Exception):
        return UTC


def utc_today_start() -> datetime:
    """UTC 자정. 조회수 일일 중복 제거처럼 날짜 단위 dedupe에 쓴다."""
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
