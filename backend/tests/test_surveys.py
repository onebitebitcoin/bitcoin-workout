"""Survey API 테스트 (스펙 §10 백엔드 케이스 전체)."""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# ─── 공통 헬퍼 ────────────────────────────────────────────────────────────────


def _reg(client: TestClient, email: str = "a@x.com", username: str = "au") -> tuple[str, dict]:
    res = client.post(
        "/api/v1/auth/register",
        json={"email": email, "username": username, "password": "password123"},
    )
    data = res.json()["data"]
    return data["access_token"], data["user"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_admin(db: Session, email: str) -> None:
    from app.models.user import User

    user = db.query(User).filter(User.email == email).first()
    if user:
        user.is_admin = True
        db.commit()


def _reg_admin(
    client: TestClient,
    db: Session,
    email: str = "admin@x.com",
    username: str = "admin",
) -> str:
    token, _ = _reg(client, email=email, username=username)
    _make_admin(db, email)
    return token


def _create_survey(
    client: TestClient,
    admin_token: str,
    title: str = "Test Survey",
    questions: list | None = None,
) -> dict:
    """어드민으로 설문을 생성하고 survey dict를 반환."""
    payload = {"title": title, "questions": questions or []}
    res = client.post("/api/v1/surveys", json=payload, headers=_auth(admin_token))
    assert res.status_code == 200, res.text
    return res.json()["data"]["survey"]


# ─── 어드민: 설문 생성 ────────────────────────────────────────────────────────


def test_admin_create_survey_returns_slug(client: TestClient, db: Session) -> None:
    admin_token = _reg_admin(client, db)
    survey = _create_survey(client, admin_token, title="My Survey")
    assert survey["title"] == "My Survey"
    assert isinstance(survey["slug"], str) and len(survey["slug"]) > 0
    assert survey["is_open"] is True
    assert survey["is_active"] is True


def test_admin_create_survey_with_questions(client: TestClient, db: Session) -> None:
    admin_token = _reg_admin(client, db)
    questions = [
        {
            "id": "q1",
            "type": "scale",
            "title": "Rate us",
            "required": True,
            "scale_min": 1,
            "scale_max": 5,
        }
    ]
    survey = _create_survey(client, admin_token, questions=questions)
    assert len(survey["questions"]) == 1
    assert survey["questions"][0]["id"] == "q1"


# ─── 공개: 활성 설문 GET ──────────────────────────────────────────────────────


def test_public_get_active_survey(client: TestClient, db: Session) -> None:
    admin_token = _reg_admin(client, db)
    questions = [
        {
            "id": "q_scale",
            "type": "scale",
            "title": "Rate us",
            "required": True,
            "scale_min": 1,
            "scale_max": 5,
        }
    ]
    survey = _create_survey(client, admin_token, title="Public Survey", questions=questions)
    slug = survey["slug"]

    res = client.get(f"/api/v1/surveys/public/{slug}")
    assert res.status_code == 200
    data = res.json()["data"]["survey"]
    assert data["title"] == "Public Survey"
    assert data["is_active"] is True
    assert len(data["questions"]) == 1
    # 공개 응답에는 title/description/questions/is_active/closes_at/id/slug 포함
    assert "id" in data
    assert "slug" in data


def test_public_get_survey_not_found(client: TestClient, db: Session) -> None:
    res = client.get("/api/v1/surveys/public/no-such-slug")
    assert res.status_code == 404


# ─── 공개: 제출 valid ─────────────────────────────────────────────────────────


def test_submit_valid_response_stored_and_anonymous(client: TestClient, db: Session) -> None:
    from app.models.survey import Survey, SurveyResponse

    admin_token = _reg_admin(client, db)
    questions = [
        {
            "id": "q_scale",
            "type": "scale",
            "title": "Rate",
            "required": True,
            "scale_min": 1,
            "scale_max": 5,
        }
    ]
    survey_data = _create_survey(client, admin_token, questions=questions)
    slug = survey_data["slug"]

    res = client.post(
        f"/api/v1/surveys/public/{slug}/responses",
        json={"answers": {"q_scale": 4}},
    )
    assert res.status_code == 200
    assert res.json()["data"]["submitted"] is True

    # DB 저장 확인
    survey_obj = db.query(Survey).filter(Survey.slug == slug).first()
    responses = db.query(SurveyResponse).filter(SurveyResponse.survey_id == survey_obj.id).all()
    assert len(responses) == 1
    assert responses[0].answers["q_scale"] == 4

    # 익명성 확인: SurveyResponse 모델에 user_id 컬럼 없음
    assert not hasattr(responses[0], "user_id")


def test_submit_with_unknown_qid_dropped(client: TestClient, db: Session) -> None:
    from app.models.survey import Survey, SurveyResponse

    admin_token = _reg_admin(client, db)
    survey_data = _create_survey(client, admin_token, questions=[])
    slug = survey_data["slug"]

    # 알 수 없는 qid 포함해 제출 → 드롭되어 저장
    res = client.post(
        f"/api/v1/surveys/public/{slug}/responses",
        json={"answers": {"unknown_q": "value"}},
    )
    assert res.status_code == 200
    survey_obj = db.query(Survey).filter(Survey.slug == slug).first()
    responses = db.query(SurveyResponse).filter(SurveyResponse.survey_id == survey_obj.id).all()
    assert len(responses) == 1
    assert "unknown_q" not in responses[0].answers


# ─── 공개: 필수 누락 → 422 ────────────────────────────────────────────────────


def test_submit_missing_required_field(client: TestClient, db: Session) -> None:
    admin_token = _reg_admin(client, db)
    questions = [
        {
            "id": "q_required",
            "type": "text",
            "title": "Tell us",
            "required": True,
        }
    ]
    survey_data = _create_survey(client, admin_token, questions=questions)
    slug = survey_data["slug"]

    res = client.post(
        f"/api/v1/surveys/public/{slug}/responses",
        json={"answers": {}},
    )
    assert res.status_code == 422


def test_submit_required_scale_out_of_range(client: TestClient, db: Session) -> None:
    admin_token = _reg_admin(client, db)
    questions = [
        {
            "id": "q_scale",
            "type": "scale",
            "title": "Rate",
            "required": True,
            "scale_min": 1,
            "scale_max": 5,
        }
    ]
    survey_data = _create_survey(client, admin_token, questions=questions)
    slug = survey_data["slug"]

    res = client.post(
        f"/api/v1/surveys/public/{slug}/responses",
        json={"answers": {"q_scale": 10}},
    )
    assert res.status_code == 422


def test_submit_single_invalid_option(client: TestClient, db: Session) -> None:
    admin_token = _reg_admin(client, db)
    questions = [
        {
            "id": "q_single",
            "type": "single",
            "title": "Choose",
            "required": True,
            "options": ["A", "B"],
        }
    ]
    survey_data = _create_survey(client, admin_token, questions=questions)
    slug = survey_data["slug"]

    res = client.post(
        f"/api/v1/surveys/public/{slug}/responses",
        json={"answers": {"q_single": "Z"}},
    )
    assert res.status_code == 422


# ─── 공개: 닫힌 설문 → 410 ───────────────────────────────────────────────────


def test_submit_closed_survey(client: TestClient, db: Session) -> None:
    admin_token = _reg_admin(client, db)
    survey_data = _create_survey(client, admin_token)
    survey_id = survey_data["id"]
    slug = survey_data["slug"]

    # 설문 종료
    close_res = client.post(
        f"/api/v1/surveys/{survey_id}/close", headers=_auth(admin_token)
    )
    assert close_res.status_code == 200
    assert close_res.json()["data"]["survey"]["is_open"] is False

    # 종료된 설문에 제출 시도
    res = client.post(
        f"/api/v1/surveys/public/{slug}/responses",
        json={"answers": {}},
    )
    assert res.status_code == 410


def test_public_get_closed_survey_returns_200(client: TestClient, db: Session) -> None:
    """종료된 설문도 공개 GET은 200 반환 (프론트가 종료 화면 표시)."""
    admin_token = _reg_admin(client, db)
    survey_data = _create_survey(client, admin_token)
    survey_id = survey_data["id"]
    slug = survey_data["slug"]

    client.post(f"/api/v1/surveys/{survey_id}/close", headers=_auth(admin_token))

    res = client.get(f"/api/v1/surveys/public/{slug}")
    assert res.status_code == 200
    assert res.json()["data"]["survey"]["is_active"] is False


# ─── 어드민: 응답 목록 및 집계 ───────────────────────────────────────────────


def test_admin_responses_count_and_aggregate(client: TestClient, db: Session) -> None:
    admin_token = _reg_admin(client, db)
    questions = [
        {
            "id": "q_scale",
            "type": "scale",
            "title": "Rate",
            "required": True,
            "scale_min": 1,
            "scale_max": 5,
        },
        {
            "id": "q_single",
            "type": "single",
            "title": "Choice",
            "required": False,
            "options": ["A", "B", "C"],
        },
        {
            "id": "q_text",
            "type": "text",
            "title": "Comment",
            "required": False,
        },
    ]
    survey_data = _create_survey(client, admin_token, questions=questions)
    survey_id = survey_data["id"]
    slug = survey_data["slug"]

    # 응답 2개 제출
    client.post(
        f"/api/v1/surveys/public/{slug}/responses",
        json={"answers": {"q_scale": 4, "q_single": "A", "q_text": "nice"}},
    )
    client.post(
        f"/api/v1/surveys/public/{slug}/responses",
        json={"answers": {"q_scale": 2, "q_single": "B"}},
    )

    res = client.get(f"/api/v1/surveys/{survey_id}/responses", headers=_auth(admin_token))
    assert res.status_code == 200
    data = res.json()["data"]

    assert data["count"] == 2
    assert len(data["responses"]) == 2

    # 개별 응답에 answers 포함
    for r in data["responses"]:
        assert "answers" in r
        assert "created_at" in r

    agg = data["aggregate"]

    # scale 집계
    assert "q_scale" in agg
    assert agg["q_scale"]["avg"] == 3.0
    assert agg["q_scale"]["count"] == 2
    assert "distribution" in agg["q_scale"]
    assert agg["q_scale"]["distribution"]["4"] == 1
    assert agg["q_scale"]["distribution"]["2"] == 1

    # single 집계
    assert "q_single" in agg
    assert agg["q_single"]["A"] == 1
    assert agg["q_single"]["B"] == 1
    assert agg["q_single"]["C"] == 0

    # text는 집계 생략
    assert "q_text" not in agg


def test_admin_responses_multi_aggregate(client: TestClient, db: Session) -> None:
    admin_token = _reg_admin(client, db)
    questions = [
        {
            "id": "q_multi",
            "type": "multi",
            "title": "Pick all",
            "required": False,
            "options": ["X", "Y", "Z"],
        }
    ]
    survey_data = _create_survey(client, admin_token, questions=questions)
    survey_id = survey_data["id"]
    slug = survey_data["slug"]

    client.post(
        f"/api/v1/surveys/public/{slug}/responses",
        json={"answers": {"q_multi": ["X", "Y"]}},
    )
    client.post(
        f"/api/v1/surveys/public/{slug}/responses",
        json={"answers": {"q_multi": ["Y", "Z"]}},
    )

    res = client.get(f"/api/v1/surveys/{survey_id}/responses", headers=_auth(admin_token))
    agg = res.json()["data"]["aggregate"]
    assert agg["q_multi"]["X"] == 1
    assert agg["q_multi"]["Y"] == 2
    assert agg["q_multi"]["Z"] == 1


# ─── 비어드민: 어드민 엔드포인트 접근 → 403 ──────────────────────────────────


def test_non_admin_create_forbidden(client: TestClient, db: Session) -> None:
    user_token, _ = _reg(client, email="user@x.com", username="user1")
    res = client.post(
        "/api/v1/surveys",
        json={"title": "Survey", "questions": []},
        headers=_auth(user_token),
    )
    assert res.status_code == 403


def test_non_admin_list_forbidden(client: TestClient, db: Session) -> None:
    user_token, _ = _reg(client, email="user@x.com", username="user1")
    res = client.get("/api/v1/surveys", headers=_auth(user_token))
    assert res.status_code == 403


def test_non_admin_get_responses_forbidden(client: TestClient, db: Session) -> None:
    admin_token = _reg_admin(client, db)
    survey_data = _create_survey(client, admin_token)
    survey_id = survey_data["id"]

    user_token, _ = _reg(client, email="user@x.com", username="user1")
    res = client.get(
        f"/api/v1/surveys/{survey_id}/responses", headers=_auth(user_token)
    )
    assert res.status_code == 403


def test_non_admin_close_forbidden(client: TestClient, db: Session) -> None:
    admin_token = _reg_admin(client, db)
    survey_data = _create_survey(client, admin_token)
    survey_id = survey_data["id"]

    user_token, _ = _reg(client, email="user@x.com", username="user1")
    res = client.post(
        f"/api/v1/surveys/{survey_id}/close", headers=_auth(user_token)
    )
    assert res.status_code == 403


# ─── 익명성: response에 user_id 없음 ──────────────────────────────────────────


def test_response_is_anonymous_no_user_id(client: TestClient, db: Session) -> None:
    from app.models.survey import SurveyResponse

    admin_token = _reg_admin(client, db)
    user_token, _ = _reg(client, email="user@x.com", username="user1")

    survey_data = _create_survey(client, admin_token)
    slug = survey_data["slug"]

    # 로그인한 사용자가 제출해도 익명으로 저장
    res = client.post(
        f"/api/v1/surveys/public/{slug}/responses",
        json={"answers": {}},
        headers=_auth(user_token),
    )
    assert res.status_code == 200

    all_responses = db.query(SurveyResponse).all()
    assert len(all_responses) == 1
    # user_id 컬럼이 아예 존재하지 않아야 함
    assert not hasattr(all_responses[0], "user_id")


def test_response_is_anonymous_no_login(client: TestClient, db: Session) -> None:
    """비로그인 사용자도 제출 가능 (익명)."""
    from app.models.survey import SurveyResponse

    admin_token = _reg_admin(client, db)
    survey_data = _create_survey(client, admin_token)
    slug = survey_data["slug"]

    res = client.post(
        f"/api/v1/surveys/public/{slug}/responses",
        json={"answers": {}},
    )
    assert res.status_code == 200
    assert db.query(SurveyResponse).count() == 1


# ─── 어드민: 설문 CRUD ────────────────────────────────────────────────────────


def test_admin_list_surveys(client: TestClient, db: Session) -> None:
    admin_token = _reg_admin(client, db)
    _create_survey(client, admin_token, title="S1")
    _create_survey(client, admin_token, title="S2")

    res = client.get("/api/v1/surveys", headers=_auth(admin_token))
    assert res.status_code == 200
    surveys = res.json()["data"]["surveys"]
    assert len(surveys) == 2
    # response_count 포함
    for s in surveys:
        assert "response_count" in s


def test_admin_get_survey_detail(client: TestClient, db: Session) -> None:
    admin_token = _reg_admin(client, db)
    survey_data = _create_survey(client, admin_token, title="Detail")
    survey_id = survey_data["id"]

    res = client.get(f"/api/v1/surveys/{survey_id}", headers=_auth(admin_token))
    assert res.status_code == 200
    data = res.json()["data"]["survey"]
    assert data["title"] == "Detail"
    assert "questions" in data
    assert "is_open" in data


def test_admin_update_survey(client: TestClient, db: Session) -> None:
    admin_token = _reg_admin(client, db)
    survey_data = _create_survey(client, admin_token, title="Original")
    survey_id = survey_data["id"]

    res = client.put(
        f"/api/v1/surveys/{survey_id}",
        json={"title": "Updated"},
        headers=_auth(admin_token),
    )
    assert res.status_code == 200
    assert res.json()["data"]["survey"]["title"] == "Updated"


def test_admin_delete_survey(client: TestClient, db: Session) -> None:
    from app.models.survey import Survey

    admin_token = _reg_admin(client, db)
    survey_data = _create_survey(client, admin_token)
    survey_id = survey_data["id"]

    res = client.delete(f"/api/v1/surveys/{survey_id}", headers=_auth(admin_token))
    assert res.status_code == 200
    assert res.json()["data"]["deleted"] is True

    # DB에서 삭제됨
    assert db.get(Survey, survey_id) is None
