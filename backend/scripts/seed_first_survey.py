"""첫 설문 시드 스크립트 — 멱등 실행 가능.

title='스택헬스 한 달 사용 설문' 인 설문이 이미 있으면 skip 후 기존 URL 출력.
실행: cd backend && .venv/bin/python scripts/seed_first_survey.py
"""

import sys
import os
from datetime import datetime
from zoneinfo import ZoneInfo

# backend/ 루트를 sys.path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal  # noqa: E402
from app.models.survey import Survey  # noqa: E402
from app.services.share_token import generate_share_token  # noqa: E402

TITLE = "스택헬스 한 달 사용 설문"
# TITLE은 프로덕션에 이미 시드된 설문과 대조하는 멱등성 키다. 바꾸면 재실행 시
# 기존 설문을 못 찾고 중복 생성한다 — 리브랜딩 후에도 원문 그대로 둔다.
PUBLIC_BASE = "https://bitcoiners.life/survey"
MAX_SLUG_RETRIES = 5

KST = ZoneInfo("Asia/Seoul")
# 2026-06-28 23:59:59 KST → UTC
CLOSES_AT_KST = datetime(2026, 6, 28, 23, 59, 59, tzinfo=KST)
CLOSES_AT_UTC = CLOSES_AT_KST.astimezone(ZoneInfo("UTC"))

QUESTIONS = [
    {
        "id": "q_satisfaction",
        "type": "scale",
        "title": "스택헬스 전반 만족도는?",
        "description": None,
        "required": True,
        "scale_min": 1,
        "scale_max": 5,
        "scale_min_label": "매우 불만족",
        "scale_max_label": "매우 만족",
    },
    {
        "id": "q_nps",
        "type": "scale",
        "title": "친구·지인에게 추천할 의향은?",
        "description": None,
        "required": True,
        "scale_min": 1,
        "scale_max": 5,
        "scale_min_label": "전혀 추천 안 함",
        "scale_max_label": "적극 추천",
    },
    {
        "id": "q_top_feature",
        "type": "single",
        "title": "가장 자주 사용하는 기능은?",
        "description": None,
        "required": True,
        "options": ["영상 시청", "영상 업로드", "댓글·답글", "좋아요·저장", "프로필·팔로우"],
    },
    {
        "id": "q_upload_ease",
        "type": "single",
        "title": "영상 업로드 과정은 쉬웠나요?",
        "description": None,
        "required": True,
        "options": ["매우 어려움", "어려움", "보통", "쉬움", "매우 쉬움", "업로드한 적 없음"],
    },
    {
        "id": "q_comment_sat",
        "type": "single",
        "title": "댓글/답글 기능 만족도는?",
        "description": None,
        "required": True,
        "options": ["매우 불만족", "불만족", "보통", "만족", "매우 만족", "사용한 적 없음"],
    },
    {
        "id": "q_feed_fit",
        "type": "scale",
        "title": "피드 추천 영상이 내 관심사와 잘 맞나요?",
        "description": None,
        "required": True,
        "scale_min": 1,
        "scale_max": 5,
        "scale_min_label": "전혀 안 맞음",
        "scale_max_label": "매우 잘 맞음",
    },
    {
        "id": "q_habit_help",
        "type": "scale",
        "title": "스택헬스가 운동 습관 유지에 도움이 됐나요?",
        "description": None,
        "required": True,
        "scale_min": 1,
        "scale_max": 5,
        "scale_min_label": "전혀 도움 안 됨",
        "scale_max_label": "매우 도움 됨",
    },
    {
        "id": "q_freq_change",
        "type": "single",
        "title": "한 달 전과 비교해 운동 빈도 변화는?",
        "description": None,
        "required": True,
        "options": ["많이 늘었다", "약간 늘었다", "비슷하다", "줄었다"],
    },
    {
        "id": "q_continue",
        "type": "scale",
        "title": "앞으로도 계속 사용할 의향이 있나요?",
        "description": None,
        "required": True,
        "scale_min": 1,
        "scale_max": 5,
        "scale_min_label": "전혀 없음",
        "scale_max_label": "매우 높음",
    },
    {
        "id": "q_speed",
        "type": "single",
        "title": "앱 속도·로딩에 불편함이 있었나요?",
        "description": None,
        "required": True,
        "options": ["매우 불편", "불편", "보통", "쾌적", "매우 쾌적"],
    },
    {
        "id": "q_intuitive",
        "type": "scale",
        "title": "화면 구성·메뉴가 직관적이었나요?",
        "description": None,
        "required": True,
        "scale_min": 1,
        "scale_max": 5,
        "scale_min_label": "매우 헷갈림",
        "scale_max_label": "매우 직관적",
    },
    {
        "id": "q_bug",
        "type": "single",
        "title": "사용 중 오류·버그를 경험했나요?",
        "description": None,
        "required": True,
        "options": ["없음", "가끔 있음", "자주 있음"],
    },
    {
        "id": "q_bug_detail",
        "type": "text",
        "title": "어떤 오류였나요? (선택)",
        "description": None,
        "required": False,
    },
    {
        "id": "q_like_most",
        "type": "text",
        "title": "가장 마음에 드는 점 하나는?",
        "description": None,
        "required": False,
    },
    {
        "id": "q_improve",
        "type": "text",
        "title": "가장 불편했거나 개선했으면 하는 점은?",
        "description": None,
        "required": False,
    },
    {
        "id": "q_feature_request",
        "type": "text",
        "title": "추가됐으면 하는 기능이 있나요?",
        "description": None,
        "required": False,
    },
    {
        "id": "q_quit_moment",
        "type": "text",
        "title": "그만두고 싶었던 순간이 있었나요? 있다면 이유는?",
        "description": None,
        "required": False,
    },
    {
        "id": "q_purpose",
        "type": "single",
        "title": "주 운동 목적은?",
        "description": None,
        "required": False,
        "options": ["다이어트", "근력·벌크업", "건강 유지", "재미·기록 공유"],
    },
]


def _generate_unique_slug(db) -> str:
    """slug 충돌 시 최대 MAX_SLUG_RETRIES 회 재생성."""
    for _ in range(MAX_SLUG_RETRIES):
        slug = generate_share_token(0)
        conflict = db.query(Survey).filter(Survey.slug == slug).first()
        if conflict is None:
            return slug
    raise RuntimeError("slug 유일성 확보 실패 — 재시도 횟수 초과")


def main() -> None:
    db = SessionLocal()
    try:
        existing = db.query(Survey).filter(Survey.title == TITLE).first()
        if existing is not None:
            import logging
            logging.getLogger(__name__).info(
                "[SKIP] title='%s' 이미 존재합니다. (id=%s, slug='%s')",
                TITLE, existing.id, existing.slug,
            )
            print(f"[SKIP] title='{TITLE}' 이미 존재합니다. (id={existing.id}, slug='{existing.slug}')")
            print(f"공개 URL: {PUBLIC_BASE}/{existing.slug}")
            return

        slug = _generate_unique_slug(db)

        survey = Survey(
            slug=slug,
            title=TITLE,
            description=(
                "한 달 이상 스택헬스를 사용해 주셔서 감사합니다. "
                "더 나은 서비스를 위한 익명 설문입니다. (약 2~3분)"
            ),
            questions=QUESTIONS,
            is_open=True,
            closes_at=CLOSES_AT_UTC,
            created_by=None,
        )
        db.add(survey)
        db.commit()
        db.refresh(survey)
        print(f"[OK] 설문 생성 완료. id={survey.id}, slug='{survey.slug}'")
        print(f"closes_at (UTC): {survey.closes_at}")
        print(f"공개 URL: {PUBLIC_BASE}/{survey.slug}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
