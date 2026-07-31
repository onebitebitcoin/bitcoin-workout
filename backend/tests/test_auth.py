from __future__ import annotations

from fastapi.testclient import TestClient


def test_register_success(client: TestClient) -> None:
    res = client.post("/api/v1/auth/register", json={
        "email": "test@example.com",
        "username": "testuser",
        "password": "password123",
    })
    assert res.status_code == 200
    data = res.json()["data"]
    assert "access_token" in data
    assert data["user"]["email"] == "test@example.com"
    assert data["user"]["username"] == "testuser"


def test_register_duplicate_email(client: TestClient) -> None:
    payload = {"email": "dup@example.com", "username": "user1", "password": "password123"}
    client.post("/api/v1/auth/register", json=payload)
    res = client.post("/api/v1/auth/register", json={**payload, "username": "user2"})
    assert res.status_code == 400


def test_login_success(client: TestClient) -> None:
    client.post("/api/v1/auth/register", json={
        "email": "login@example.com", "username": "loginuser", "password": "secret123",
    })
    res = client.post("/api/v1/auth/login", json={
        "email": "login@example.com", "password": "secret123",
    })
    assert res.status_code == 200
    assert "access_token" in res.json()["data"]


def test_login_wrong_password(client: TestClient) -> None:
    client.post("/api/v1/auth/register", json={
        "email": "pw@example.com", "username": "pwuser", "password": "correct123",
    })
    res = client.post("/api/v1/auth/login", json={
        "email": "pw@example.com", "password": "wrong",
    })
    assert res.status_code == 401


def test_get_me_valid_token(client: TestClient) -> None:
    reg = client.post("/api/v1/auth/register", json={
        "email": "me@example.com", "username": "meuser", "password": "password123",
    })
    token = reg.json()["data"]["access_token"]
    res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["data"]["email"] == "me@example.com"


def test_get_me_no_token(client: TestClient) -> None:
    res = client.get("/api/v1/auth/me")
    assert res.status_code == 401


def test_patch_me_lightning_address(client: TestClient) -> None:
    reg = client.post("/api/v1/auth/register", json={
        "email": "ln@example.com", "username": "lnuser", "password": "password123",
    })
    token = reg.json()["data"]["access_token"]
    res = client.patch(
        "/api/v1/auth/me",
        json={"lightning_address": "lnuser@walletofsatoshi.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json()["data"]["lightning_address"] == "lnuser@walletofsatoshi.com"


# ── Google OAuth ──────────────────────────────────────────────────────

def test_google_login_not_configured(client: TestClient, monkeypatch) -> None:
    import app.routes.auth as auth_module
    monkeypatch.setattr(auth_module.settings, "google_client_id", "")
    res = client.get("/api/v1/auth/google", follow_redirects=False)
    assert res.status_code == 503


def test_google_login_redirects_when_configured(client: TestClient, monkeypatch) -> None:
    import app.routes.auth as auth_module
    monkeypatch.setattr(auth_module.settings, "google_client_id", "fake-client-id")
    res = client.get("/api/v1/auth/google", follow_redirects=False)
    assert res.status_code in (302, 307)
    assert "accounts.google.com" in res.headers["location"]


def test_google_callback_failure(client: TestClient, monkeypatch) -> None:
    import app.routes.auth as auth_module
    monkeypatch.setattr(auth_module.settings, "frontend_url", "http://localhost:5173")
    # No mock for exchange_code — it will fail with network error
    res = client.get("/api/v1/auth/google/callback?code=badcode", follow_redirects=False)
    assert res.status_code in (302, 307)
    assert "google_auth_failed" in res.headers["location"]


# ── LNAuth ────────────────────────────────────────────────────────────

def test_lnauth_challenge_returns_k1_and_lnurl(client: TestClient) -> None:
    res = client.get("/api/v1/auth/lnauth/challenge")
    assert res.status_code == 200
    data = res.json()["data"]
    assert "k1" in data
    assert "lnurl" in data
    assert len(data["k1"]) == 64
    assert data["lnurl"].startswith("LNURL")


def test_lnauth_callback_invalid_k1(client: TestClient) -> None:
    res = client.get("/api/v1/auth/lnauth?tag=login&k1=deadbeef00000000000000000000000000000000000000000000000000000000")
    assert res.status_code == 400


def test_lnauth_callback_metadata_response(client: TestClient) -> None:
    challenge_res = client.get("/api/v1/auth/lnauth/challenge")
    k1 = challenge_res.json()["data"]["k1"]
    res = client.get(f"/api/v1/auth/lnauth?tag=login&k1={k1}")
    assert res.status_code == 200
    body = res.json()
    assert body["tag"] == "login"
    assert body["k1"] == k1


def test_lnauth_callback_invalid_signature(client: TestClient) -> None:
    challenge_res = client.get("/api/v1/auth/lnauth/challenge")
    k1 = challenge_res.json()["data"]["k1"]
    # Use a valid compressed pubkey format but garbage sig
    fake_key = "02" + "ab" * 32
    fake_sig = "30" + "44" + "02" * 68
    res = client.get(f"/api/v1/auth/lnauth?tag=login&k1={k1}&sig={fake_sig}&key={fake_key}")
    assert res.status_code == 200
    assert res.json()["status"] == "ERROR"


def test_lnauth_verify_not_verified(client: TestClient) -> None:
    challenge_res = client.get("/api/v1/auth/lnauth/challenge")
    k1 = challenge_res.json()["data"]["k1"]
    res = client.get(f"/api/v1/auth/lnauth/verify?k1={k1}")
    assert res.status_code == 200
    assert res.json()["data"]["verified"] is False


def test_lnauth_verify_unknown_k1(client: TestClient) -> None:
    res = client.get("/api/v1/auth/lnauth/verify?k1=" + "00" * 32)
    assert res.status_code == 200
    assert res.json()["data"]["verified"] is False


# ── Existing tests ────────────────────────────────────────────────────

def test_password_not_stored_plaintext(client: TestClient) -> None:
    from app.models.user import User

    client.post("/api/v1/auth/register", json={
        "email": "hash@example.com", "username": "hashuser", "password": "mypassword",
    })

    # Directly query in-memory DB to verify bcrypt hash
    from tests.conftest import TestingSession
    with TestingSession() as s:
        user = s.query(User).filter(User.email == "hash@example.com").first()
        assert user is not None
        assert user.password_hash != "mypassword"
        assert user.password_hash.startswith("$2b$")


def test_google_oauth_state_verification_fails_closed_without_redis(monkeypatch) -> None:
    from app.services import google_oauth

    def raise_redis_unavailable():
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr("app.services.job_queue.get_redis_client", raise_redis_unavailable)
    assert google_oauth.verify_oauth_state("state-token") is False


def test_register_short_password_returns_user_friendly_message(client: TestClient) -> None:
    res = client.post("/api/v1/auth/register", json={
        "email": "shortpw@example.com",
        "username": "shortpw",
        "password": "short",
    })
    assert res.status_code == 422
    assert res.json()["detail"] == "비밀번호는 8자 이상 입력해주세요."
    assert "String should" not in str(res.json())


def test_register_invalid_email_returns_user_friendly_message(client: TestClient) -> None:
    res = client.post("/api/v1/auth/register", json={
        "email": "not-an-email",
        "username": "emailuser",
        "password": "password123",
    })
    assert res.status_code == 422
    assert res.json()["detail"] == "이메일 형식이 올바르지 않습니다."
    assert "value is not" not in str(res.json())


# ── Refresh token ─────────────────────────────────────────────────────

def _register(client: TestClient, email: str = "refresh@example.com") -> dict:
    res = client.post("/api/v1/auth/register", json={
        "email": email, "username": email.split("@")[0], "password": "password123",
    })
    assert res.status_code == 200
    return res.json()["data"]


def test_register_returns_refresh_token(client: TestClient) -> None:
    data = _register(client)
    assert data["refresh_token"]
    assert data["access_token"] != data["refresh_token"]


def test_login_returns_refresh_token(client: TestClient) -> None:
    client.post("/api/v1/auth/register", json={
        "email": "loginref@example.com", "username": "loginref", "password": "password123",
    })
    res = client.post("/api/v1/auth/login", json={
        "email": "loginref@example.com", "password": "password123",
    })
    assert res.json()["data"]["refresh_token"]


def test_refresh_issues_new_tokens(client: TestClient) -> None:
    refresh = _register(client, "r1@example.com")["refresh_token"]
    res = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["access_token"]
    assert data["refresh_token"]
    # 새 access token으로 /me 접근 가능
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {data['access_token']}"})
    assert me.status_code == 200


def test_refresh_rejects_access_token(client: TestClient) -> None:
    # access token을 refresh 엔드포인트에 쓰면 거부 (type 검증)
    access = _register(client, "r2@example.com")["access_token"]
    res = client.post("/api/v1/auth/refresh", json={"refresh_token": access})
    assert res.status_code == 401


def test_access_endpoint_rejects_refresh_token(client: TestClient) -> None:
    # refresh token으로 보호된 엔드포인트 접근 불가 (type 검증)
    refresh = _register(client, "r3@example.com")["refresh_token"]
    res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {refresh}"})
    assert res.status_code == 401


def test_refresh_rejects_garbage_token(client: TestClient) -> None:
    res = client.post("/api/v1/auth/refresh", json={"refresh_token": "not-a-jwt"})
    assert res.status_code == 401
