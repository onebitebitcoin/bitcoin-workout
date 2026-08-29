"""날짜 경계 계산 유틸.

"이 기록이 며칠 자인가"는 서비스 전체가 하나의 기준으로 정한다 — 한국 시간(KST).

예전에는 클라이언트가 요청마다 자기 타임존을 실어 보내고(`?timezone=`,
`X-Client-Timezone`) 서버가 그때그때 파싱했다. 그 구조는 영상 확정 기능의 글로벌 UTC
집계 요구에서 나온 것인데 그 기능이 사라지면서 근거도 같이 없어졌고, 남은 건 같은 날짜를
요청마다 다르게 계산할 여지뿐이었다. 기준을 상수 하나로 고정하면 캘린더·스트릭·
나무 단계·일일 제한이 전부 같은 날짜를 본다.

저장은 그대로 UTC다(모든 datetime 컬럼은 timezone-aware). 여기서 정하는 것은
"UTC로 저장된 시각을 며칠로 셀 것인가"뿐이다.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# 서비스의 하루 경계. 이 값을 바꾸면 캘린더·스트릭·나무 단계·일일 제한이 함께 움직인다.
SERVICE_TZ = ZoneInfo("Asia/Seoul")


def now_local() -> datetime:
    """서비스 기준 시간대의 현재 시각."""
    return datetime.now(SERVICE_TZ)


def to_local_date(dt: datetime) -> str:
    """UTC로 저장된 시각을 서비스 기준 날짜 문자열(YYYY-MM-DD)로 바꾼다."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(SERVICE_TZ).strftime("%Y-%m-%d")


def today_start() -> datetime:
    """서비스 기준 오늘 자정에 해당하는 UTC 시각.

    일일 제한(댓글·업로드)과 조회수 중복 제거처럼 "오늘 안에서" 세는 곳에 쓴다.
    DB의 created_at 은 UTC 라서 비교 대상도 UTC 여야 한다.
    """
    local_midnight = now_local().replace(hour=0, minute=0, second=0, microsecond=0)
    return local_midnight.astimezone(timezone.utc)
