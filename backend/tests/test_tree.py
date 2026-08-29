from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.post import Post
from app.models.video import Video

BASELINE = 100_000_000


def _register(client: TestClient, email: str, username: str) -> tuple[str, dict]:
    res = client.post("/api/v1/auth/register", json={"email": email, "username": username, "password": "password123"})
    data = res.json()["data"]
    return data["access_token"], data["user"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _seed_post(db: Session, user_id: int, *, days_ago: int = 0, btc_price_krw: int | None = None) -> Post:
    """지정한 날짜(UTC, 오늘로부터 days_ago일 전)에 활성 게시물 하나를 직접 심는다."""
    created_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
    video = Video(
        user_id=user_id,
        r2_key=f"videos/{user_id}/seed-{days_ago}-{btc_price_krw}.mp4",
        cdn_url="https://cdn/seed.mp4",
        file_hash=f"hash-{user_id}-{days_ago}-{btc_price_krw}",
        duration_sec=20,
        status="active",
        created_at=created_at,
    )
    db.add(video)
    db.flush()
    post = Post(
        video_id=video.id,
        user_id=user_id,
        # 운영용 generate_share_token()을 쓰지 않는다. 그 토큰은 (초 단위 시각 + user_id +
        # 16비트 난수) 조합이라, 한 사용자로 100건을 같은 초에 심는 이 헬퍼에서는 생일 문제로
        # 충돌한다(share_token UNIQUE 위반으로 테스트가 간헐 실패했다). 실제 업로드는 건당
        # 수 초 이상 걸려 이 조건에 걸리지 않으므로 운영 로직 문제는 아니다.
        share_token=f"seed-{uuid4().hex[:14]}",
        btc_price_krw=btc_price_krw,
        created_at=created_at,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


def _seed_days(db: Session, user_id: int, n: int) -> None:
    """서로 다른 n개의 날짜에 게시물을 하나씩 심어 누적 기록일 수를 n으로 만든다."""
    for i in range(n):
        _seed_post(db, user_id, days_ago=i)


# ── 인증 ──────────────────────────────────────────────────────────────

def test_tree_requires_auth(client: TestClient) -> None:
    res = client.get("/api/v1/users/me/tree")
    assert res.status_code in (401, 403)


# ── stage 경계값 ──────────────────────────────────────────────────────

def test_tree_stage_seed_when_no_posts(client: TestClient) -> None:
    token, _ = _register(client, "seed@x.com", "seeduser")
    with patch("app.routes.users.get_btc_price_krw", return_value=BASELINE):
        res = client.get("/api/v1/users/me/tree", headers=_auth(token))
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["stage"] == "seed"
    assert data["total_days"] == 0
    assert data["next_stage_at"] == 1
    assert data["fruit"]["available"] is False


@pytest.mark.parametrize(
    "total_days,expected_stage,expected_next",
    [
        (1, "sprout", 7),
        (6, "sprout", 7),
        (7, "sapling", 30),
        (29, "sapling", 30),
        (30, "tree", 100),
        (99, "tree", 100),
        (100, "grand", None),
    ],
)
def test_tree_stage_boundaries(
    client: TestClient, db: Session, total_days: int, expected_stage: str, expected_next: int | None
) -> None:
    token, user = _register(client, f"tree{total_days}@x.com", f"treeuser{total_days}")
    _seed_days(db, user["id"], total_days)
    with patch("app.routes.users.get_btc_price_krw", return_value=None):
        res = client.get("/api/v1/users/me/tree", headers=_auth(token))
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["total_days"] == total_days
    assert data["stage"] == expected_stage
    assert data["next_stage_at"] == expected_next


def test_tree_stage_counts_only_own_posts(client: TestClient, db: Session) -> None:
    token_a, _user_a = _register(client, "owna@x.com", "ownusera")
    _token_b, user_b = _register(client, "ownb@x.com", "ownuserb")
    _seed_days(db, user_b["id"], 10)
    with patch("app.routes.users.get_btc_price_krw", return_value=None):
        res = client.get("/api/v1/users/me/tree", headers=_auth(token_a))
    data = res.json()["data"]
    assert data["total_days"] == 0
    assert data["stage"] == "seed"


# ── fruit 판정 ────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "current_price,expected_count,expected_size",
    [
        (75_000_000, 1, "small"),    # change -25%
        (80_000_000, 2, "small"),    # change -20% (경계값 — -20 이상은 2)
        (90_000_000, 2, "small"),    # change -10%
        (100_000_000, 3, "medium"),  # change 0%
        (119_000_000, 3, "medium"),  # change +19%
        (120_000_000, 5, "medium"),  # change +20% (경계값 — 20 이상은 5)
        (129_000_000, 5, "medium"),  # change +29%
        (130_000_000, 5, "large"),   # change +30% (size 경계값 — 30 이상은 large)
        (149_000_000, 5, "large"),   # change +49%
        (150_000_000, 7, "large"),   # change +50% (경계값 — 50 이상은 7)
        (200_000_000, 7, "large"),   # change +100%
    ],
)
def test_tree_fruit_boundaries(
    client: TestClient, db: Session, current_price: int, expected_count: int, expected_size: str
) -> None:
    token, user = _register(client, f"fruit{current_price}@x.com", f"fruituser{current_price}")
    _seed_post(db, user["id"], btc_price_krw=BASELINE)
    with patch("app.routes.users.get_btc_price_krw", return_value=current_price):
        res = client.get("/api/v1/users/me/tree", headers=_auth(token))
    fruit = res.json()["data"]["fruit"]
    assert fruit["available"] is True
    assert fruit["count"] == expected_count
    assert fruit["size"] == expected_size
    assert fruit["price_krw"] == current_price
    assert fruit["baseline_krw"] == BASELINE


def test_tree_fruit_baseline_is_average_of_stamped_posts(client: TestClient, db: Session) -> None:
    token, user = _register(client, "avg@x.com", "avguser")
    _seed_post(db, user["id"], btc_price_krw=80_000_000, days_ago=0)
    _seed_post(db, user["id"], btc_price_krw=120_000_000, days_ago=1)
    with patch("app.routes.users.get_btc_price_krw", return_value=110_000_000):
        res = client.get("/api/v1/users/me/tree", headers=_auth(token))
    fruit = res.json()["data"]["fruit"]
    assert fruit["baseline_krw"] == 100_000_000
    assert fruit["change_pct"] == 10.0


def test_tree_fruit_unavailable_when_no_stamped_price(client: TestClient, db: Session) -> None:
    """과거(가격 박제 이전) 게시물만 있는 경우 — btc_price_krw가 전부 NULL."""
    token, user = _register(client, "nostamp@x.com", "nostampuser")
    _seed_post(db, user["id"], btc_price_krw=None)
    with patch("app.routes.users.get_btc_price_krw", return_value=BASELINE):
        res = client.get("/api/v1/users/me/tree", headers=_auth(token))
    fruit = res.json()["data"]["fruit"]
    assert fruit == {
        "available": False,
        "count": 0,
        "size": "small",
        "price_krw": None,
        "baseline_krw": None,
        "change_pct": None,
    }


def test_tree_fruit_unavailable_when_price_fetch_fails(client: TestClient, db: Session) -> None:
    """baseline은 있지만 현재가 조회에 실패한 경우."""
    token, user = _register(client, "pricefail@x.com", "pricefailuser")
    _seed_post(db, user["id"], btc_price_krw=BASELINE)
    with patch("app.routes.users.get_btc_price_krw", return_value=None):
        res = client.get("/api/v1/users/me/tree", headers=_auth(token))
    fruit = res.json()["data"]["fruit"]
    assert fruit["available"] is False


# ── /videos/confirm 가격 박제 통합 ───────────────────────────────────────

def test_confirm_upload_stamps_btc_price_and_feeds_tree_baseline(client: TestClient) -> None:
    token, user = _register(client, "stamp@x.com", "stampuser")
    with patch("app.routes.videos.r2_service.get_cdn_url", return_value="https://cdn/v.mp4"), \
            patch("app.routes.videos.get_btc_price_krw", return_value=BASELINE):
        res = client.post(
            "/api/v1/videos/confirm",
            json={"r2_key": f"videos/{user['id']}/v.mp4", "duration_sec": 20},
            headers=_auth(token),
        )
    assert res.status_code == 200

    with patch("app.routes.users.get_btc_price_krw", return_value=BASELINE):
        tree_res = client.get("/api/v1/users/me/tree", headers=_auth(token))
    fruit = tree_res.json()["data"]["fruit"]
    assert fruit["available"] is True
    assert fruit["baseline_krw"] == BASELINE
    assert tree_res.json()["data"]["total_days"] == 1
    assert tree_res.json()["data"]["stage"] == "sprout"


def test_confirm_upload_succeeds_when_price_fetch_fails(client: TestClient) -> None:
    """가격 조회 실패가 업로드 자체를 막으면 안 된다."""
    token, user = _register(client, "pricedown@x.com", "pricedownuser")
    with patch("app.routes.videos.r2_service.get_cdn_url", return_value="https://cdn/v.mp4"), \
            patch("app.routes.videos.get_btc_price_krw", return_value=None):
        res = client.post(
            "/api/v1/videos/confirm",
            json={"r2_key": f"videos/{user['id']}/v.mp4", "duration_sec": 20},
            headers=_auth(token),
        )
    assert res.status_code == 200
    assert res.json()["data"]["post"] is not None


# ── btc_price 서비스 자체 견고성 (외부 HTTP는 항상 목) ─────────────────────
# 이 섹션의 테스트는 라우트 레벨 패치를 거치지 않고 get_btc_price_krw()를 직접 호출해
# 모듈 전역 인메모리 캐시/백오프 상태를 그대로 사용한다. 테스트 간 오염을 막기 위해
# 매 테스트 전후로 캐시를 초기화한다.

@pytest.fixture(autouse=True)
def _reset_btc_price_memory_cache():
    from app.services import btc_price
    btc_price._reset_cache()
    yield
    btc_price._reset_cache()


def test_get_btc_price_krw_returns_none_on_http_failure() -> None:
    from app.services import btc_price

    with patch("app.services.btc_price.httpx.get", side_effect=Exception("network down")):
        assert btc_price.get_btc_price_krw() is None


def test_get_btc_price_krw_returns_value_on_success() -> None:
    from app.services import btc_price

    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"bitcoin": {"krw": 123456789}}

    with patch("app.services.btc_price.httpx.get", return_value=_FakeResponse()):
        assert btc_price.get_btc_price_krw() == 123456789


def test_get_btc_price_krw_uses_memory_cache_when_redis_unset() -> None:
    """REDIS_URL 미설정(dev 환경 기본값)에서 연속 호출해도 외부 API는 1번만 불려야 한다.

    인메모리 캐시가 없으면 프로필을 열 때마다 CoinGecko를 직접 때려 rate limit(429)에
    바로 걸린다 — 실제로 발생했던 장애를 재현 방지한다.
    """
    from app.services import btc_price

    call_count = 0

    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"bitcoin": {"krw": 100_000_000}}

    def _fake_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return _FakeResponse()

    with patch("app.services.btc_price.httpx.get", side_effect=_fake_get):
        first = btc_price.get_btc_price_krw()
        second = btc_price.get_btc_price_krw()
        third = btc_price.get_btc_price_krw()

    assert first == second == third == 100_000_000
    assert call_count == 1


def test_get_btc_price_krw_skips_retry_during_backoff() -> None:
    """외부 API 실패(예: 429) 직후 재호출해도 백오프 동안은 다시 때리지 않는다."""
    from app.services import btc_price

    call_count = 0

    def _fake_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise httpx.HTTPError("429 Too Many Requests")

    with patch("app.services.btc_price.httpx.get", side_effect=_fake_get):
        first = btc_price.get_btc_price_krw()
        second = btc_price.get_btc_price_krw()

    assert first is None
    assert second is None
    assert call_count == 1


def test_get_btc_price_krw_falls_back_to_memory_stale_after_failure() -> None:
    """신선 TTL은 지났지만 stale TTL 안에서, 외부 API가 실패하면 인메모리 stale 값을 쓴다."""
    from app.services import btc_price

    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"bitcoin": {"krw": 90_000_000}}

    with patch("app.services.btc_price.httpx.get", return_value=_FakeResponse()):
        first = btc_price.get_btc_price_krw()
    assert first == 90_000_000

    # 신선 TTL이 이미 지난 것처럼 마지막 성공 시각을 과거로 되돌린다.
    btc_price._state["fetched_at"] -= (btc_price.CACHE_TTL + 1)

    with patch("app.services.btc_price.httpx.get", side_effect=Exception("network down")):
        second = btc_price.get_btc_price_krw()

    assert second == 90_000_000
