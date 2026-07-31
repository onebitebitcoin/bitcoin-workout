import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.survey import Survey, SurveyResponse
from app.models.user import User
from app.routes.auth import get_current_user, get_optional_user
from app.schemas.survey import (
    SurveyCreateRequest,
    SurveyResponseSubmit,
    SurveyUpdateRequest,
)
from app.services.error_codes import (
    E_ADMIN_REQUIRED,
    E_SURVEY_CLOSED,
    E_SURVEY_INVALID_ANSWER,
    E_SURVEY_NOT_FOUND,
    api_error,
)
from app.services.share_token import generate_share_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/surveys", tags=["surveys"])


# ─── Serialization helpers ────────────────────────────────────────────────────


def _survey_public_dict(survey: Survey) -> dict:
    return {
        "id": survey.id,
        "slug": survey.slug,
        "title": survey.title,
        "description": survey.description,
        "questions": survey.questions,
        "is_active": survey.is_active(),
        "closes_at": survey.closes_at.isoformat() if survey.closes_at else None,
    }


def _survey_admin_full_dict(survey: Survey) -> dict:
    return {
        "id": survey.id,
        "slug": survey.slug,
        "title": survey.title,
        "description": survey.description,
        "questions": survey.questions,
        "is_open": survey.is_open,
        "is_active": survey.is_active(),
        "closes_at": survey.closes_at.isoformat() if survey.closes_at else None,
        "created_by": survey.created_by,
        "created_at": survey.created_at.isoformat(),
        "updated_at": survey.updated_at.isoformat(),
    }


# ─── Validation helpers ───────────────────────────────────────────────────────


def _validate_answers(survey: Survey, answers: dict) -> dict:
    """
    문항 타입별 검증 후 정제된 answers dict를 반환한다.
    알 수 없는 qid는 드롭, required 누락 및 타입 위반은 422 raise.
    """
    questions: list = survey.questions or []
    valid_qids = {q["id"] for q in questions}

    # 알 수 없는 qid 드롭
    cleaned = {k: v for k, v in answers.items() if k in valid_qids}

    for q in questions:
        qid: str = q["id"]
        q_type: str = q.get("type", "text")
        required: bool = q.get("required", False)
        value = cleaned.get(qid)

        # required 체크
        if required and (value is None or value == "" or value == []):
            raise api_error(422, E_SURVEY_INVALID_ANSWER, f"필수 문항 '{qid}'에 답변이 없습니다")

        if value is None:
            continue

        # 타입별 검증
        if q_type == "scale":
            if not isinstance(value, int):
                raise api_error(422, E_SURVEY_INVALID_ANSWER, f"문항 '{qid}'의 답변은 정수여야 합니다")
            scale_min: int = q.get("scale_min", 1)
            scale_max: int = q.get("scale_max", 5)
            if not (scale_min <= value <= scale_max):
                raise api_error(
                    422,
                    E_SURVEY_INVALID_ANSWER,
                    f"문항 '{qid}'의 답변은 {scale_min}~{scale_max} 범위여야 합니다",
                )
        elif q_type == "single":
            options: list = q.get("options", [])
            if value not in options:
                raise api_error(422, E_SURVEY_INVALID_ANSWER, f"문항 '{qid}'의 답변이 유효한 옵션이 아닙니다")
        elif q_type == "multi":
            if not isinstance(value, list):
                raise api_error(422, E_SURVEY_INVALID_ANSWER, f"문항 '{qid}'의 답변은 배열이어야 합니다")
            options = q.get("options", [])
            for item in value:
                if item not in options:
                    raise api_error(
                        422,
                        E_SURVEY_INVALID_ANSWER,
                        f"문항 '{qid}'의 답변에 유효하지 않은 옵션이 있습니다",
                    )
        elif q_type == "text":
            if not isinstance(value, str):
                raise api_error(422, E_SURVEY_INVALID_ANSWER, f"문항 '{qid}'의 답변은 문자열이어야 합니다")
            if len(value) > 4000:
                raise api_error(
                    422,
                    E_SURVEY_INVALID_ANSWER,
                    f"문항 '{qid}'의 답변이 너무 깁니다 (최대 4000자)",
                )

    return cleaned


def _build_aggregate(survey: Survey, responses: list) -> dict:
    """
    single/multi: 옵션별 카운트
    scale: avg + count + distribution
    text: 생략 (개별 responses에만)
    """
    aggregate: dict = {}
    for q in (survey.questions or []):
        qid: str = q["id"]
        q_type: str = q.get("type", "text")

        if q_type == "text":
            continue

        if q_type in ("single", "multi"):
            options: list = q.get("options", [])
            counts: dict = {opt: 0 for opt in options}
            for resp in responses:
                value = resp.answers.get(qid)
                if value is None:
                    continue
                if q_type == "single":
                    if value in counts:
                        counts[value] += 1
                else:  # multi
                    if isinstance(value, list):
                        for item in value:
                            if item in counts:
                                counts[item] += 1
            aggregate[qid] = counts

        elif q_type == "scale":
            values = [
                resp.answers[qid]
                for resp in responses
                if resp.answers.get(qid) is not None and isinstance(resp.answers.get(qid), int)
            ]
            distribution: dict = {}
            for v in values:
                key = str(v)
                distribution[key] = distribution.get(key, 0) + 1
            aggregate[qid] = {
                "avg": sum(values) / len(values) if values else 0.0,
                "count": len(values),
                "distribution": distribution,
            }

    return aggregate


# ─── Public endpoints ────────────────────────────────────────────────────────


@router.get("/public/{slug}")
def get_public_survey(
    slug: str,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
) -> dict:
    survey = db.query(Survey).filter(Survey.slug == slug).first()
    if not survey:
        raise api_error(404, E_SURVEY_NOT_FOUND, "설문을 찾을 수 없습니다")
    return {"data": {"survey": _survey_public_dict(survey)}}


@router.post("/public/{slug}/responses")
def submit_survey_response(
    slug: str,
    body: SurveyResponseSubmit,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
) -> dict:
    survey = db.query(Survey).filter(Survey.slug == slug).first()
    if not survey:
        raise api_error(404, E_SURVEY_NOT_FOUND, "설문을 찾을 수 없습니다")
    if not survey.is_active():
        raise api_error(410, E_SURVEY_CLOSED, "종료된 설문입니다")

    cleaned_answers = _validate_answers(survey, body.answers)

    response = SurveyResponse(
        survey_id=survey.id,
        answers=cleaned_answers,
    )
    db.add(response)
    db.commit()
    logger.info("Survey response submitted: survey_id=%s", survey.id)
    return {"data": {"submitted": True}}


# ─── Admin endpoints ──────────────────────────────────────────────────────────


@router.get("")
def list_surveys(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not current_user.is_admin:
        raise api_error(403, E_ADMIN_REQUIRED, "관리자만 접근할 수 있습니다")
    surveys = db.query(Survey).order_by(Survey.created_at.desc()).all()
    result = []
    for survey in surveys:
        response_count = (
            db.query(SurveyResponse).filter(SurveyResponse.survey_id == survey.id).count()
        )
        result.append(
            {
                "id": survey.id,
                "slug": survey.slug,
                "title": survey.title,
                "is_open": survey.is_open,
                "is_active": survey.is_active(),
                "closes_at": survey.closes_at.isoformat() if survey.closes_at else None,
                "response_count": response_count,
                "created_at": survey.created_at.isoformat(),
            }
        )
    return {"data": {"surveys": result}}


@router.post("")
def create_survey(
    body: SurveyCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not current_user.is_admin:
        raise api_error(403, E_ADMIN_REQUIRED, "관리자만 접근할 수 있습니다")
    slug = generate_share_token(current_user.id)
    survey = Survey(
        slug=slug,
        title=body.title,
        description=body.description,
        questions=body.questions,
        closes_at=body.closes_at,
        created_by=current_user.id,
        is_open=True,
    )
    db.add(survey)
    db.commit()
    db.refresh(survey)
    logger.info("Survey created: id=%s slug=%s by user_id=%s", survey.id, survey.slug, current_user.id)
    return {"data": {"survey": _survey_admin_full_dict(survey)}}


@router.get("/{survey_id}/responses")
def get_survey_responses(
    survey_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not current_user.is_admin:
        raise api_error(403, E_ADMIN_REQUIRED, "관리자만 접근할 수 있습니다")
    survey = db.get(Survey, survey_id)
    if not survey:
        raise api_error(404, E_SURVEY_NOT_FOUND, "설문을 찾을 수 없습니다")

    responses = (
        db.query(SurveyResponse)
        .filter(SurveyResponse.survey_id == survey_id)
        .order_by(SurveyResponse.created_at.desc())
        .all()
    )
    aggregate = _build_aggregate(survey, responses)

    return {
        "data": {
            "count": len(responses),
            "responses": [
                {
                    "id": r.id,
                    "answers": r.answers,
                    "created_at": r.created_at.isoformat(),
                }
                for r in responses
            ],
            "aggregate": aggregate,
        }
    }


@router.post("/{survey_id}/close")
def close_survey(
    survey_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not current_user.is_admin:
        raise api_error(403, E_ADMIN_REQUIRED, "관리자만 접근할 수 있습니다")
    survey = db.get(Survey, survey_id)
    if not survey:
        raise api_error(404, E_SURVEY_NOT_FOUND, "설문을 찾을 수 없습니다")
    survey.is_open = False
    db.commit()
    db.refresh(survey)
    return {"data": {"survey": _survey_admin_full_dict(survey)}}


@router.get("/{survey_id}")
def get_survey(
    survey_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not current_user.is_admin:
        raise api_error(403, E_ADMIN_REQUIRED, "관리자만 접근할 수 있습니다")
    survey = db.get(Survey, survey_id)
    if not survey:
        raise api_error(404, E_SURVEY_NOT_FOUND, "설문을 찾을 수 없습니다")
    return {"data": {"survey": _survey_admin_full_dict(survey)}}


@router.put("/{survey_id}")
def update_survey(
    survey_id: int,
    body: SurveyUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not current_user.is_admin:
        raise api_error(403, E_ADMIN_REQUIRED, "관리자만 접근할 수 있습니다")
    survey = db.get(Survey, survey_id)
    if not survey:
        raise api_error(404, E_SURVEY_NOT_FOUND, "설문을 찾을 수 없습니다")
    if body.title is not None:
        survey.title = body.title
    if body.description is not None:
        survey.description = body.description
    if body.questions is not None:
        survey.questions = body.questions
    if body.closes_at is not None:
        survey.closes_at = body.closes_at
    if body.is_open is not None:
        survey.is_open = body.is_open
    db.commit()
    db.refresh(survey)
    return {"data": {"survey": _survey_admin_full_dict(survey)}}


@router.delete("/{survey_id}")
def delete_survey(
    survey_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not current_user.is_admin:
        raise api_error(403, E_ADMIN_REQUIRED, "관리자만 접근할 수 있습니다")
    survey = db.get(Survey, survey_id)
    if not survey:
        raise api_error(404, E_SURVEY_NOT_FOUND, "설문을 찾을 수 없습니다")
    db.delete(survey)
    db.commit()
    logger.info("Survey deleted: id=%s by user_id=%s", survey_id, current_user.id)
    return {"data": {"deleted": True}}
