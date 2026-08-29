"""BTC/KRW 현재가 조회 (CoinGecko, 인메모리 캐시 + Redis 캐시, 실패 백오프).

- 캐시는 **두 계층**이다: 프로세스 로컬 인메모리 캐시(항상 존재) + Redis 캐시(선택,
  여러 워커/프로세스 간 공유). Redis가 없거나 죽어도 인메모리 계층만으로 정상 동작해야
  한다 — REDIS_URL 미설정 dev 환경에서 인메모리 캐시가 없으면 프로필 화면을 몇 번만
  열어도 CoinGecko 무료 티어 rate limit(429)에 바로 걸린다.
- 외부 API가 최근에 실패했으면(백오프 윈도우 내) 재시도하지 않고 곧장 stale 값/None으로
  간다 — 429를 맞은 직후에도 요청마다 다시 때리는 걸 막기 위함이다.
- 외부 API 실패가 호출부(업로드, 프로필 조회)를 막아서는 안 되므로
  이 모듈의 공개 함수는 예외를 절대 밖으로 던지지 않고 실패 시 None을 반환한다.
- 모듈을 import하는 것만으로 네트워크/Redis 연결이 일어나지 않는다(부작용 없음) —
  worker 프로세스도 이 모듈을 import만 해두고 필요할 때 호출한다.

조회 순서: 인메모리(신선) → Redis(신선) → CoinGecko → 인메모리(stale) → Redis(stale) → None
저장: CoinGecko 조회 성공 시 인메모리와 Redis 양쪽에 쓴다.
"""
from __future__ import annotations

import logging
import time

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
REQUEST_TIMEOUT = 4.0  # seconds — 외부 API가 느려도 우리 응답까지 느려지면 안 된다

CACHE_KEY = "btc_price:krw"
CACHE_TTL = 300  # 5분 — 정상 조회 시 이 시간 동안 재사용
STALE_CACHE_KEY = "btc_price:krw:stale"
STALE_TTL = 86400  # 24시간 — 외부 API 장애 시 이 값을 마지막 값으로 사용
BACKOFF_SECONDS = 60  # 외부 API 실패 직후 이 시간 동안은 재시도하지 않는다 (예: 429 대응)

# 프로세스 로컬 캐시 상태. 락을 걸지 않는다 — uvicorn이 스레드를 여러 개 띄워도
# 경쟁 상태의 최악의 결과는 "거의 동시에 CoinGecko를 한 번 더 호출"하는 정도라
# 정합성이 깨지지 않는다(멱등 조회, 마지막에 쓴 값이 이기면 그만). 락으로 얻는
# 이득보다 코드 복잡도가 더 커서 의도적으로 생략한다.
_state: dict[str, float | int | None] = {
    "price": None,           # 마지막으로 성공한 가격(원). 신선/stale 판정에 공용으로 쓴다.
    "fetched_at": 0.0,       # 마지막 성공 시각 (time.monotonic())
    "last_failure_at": 0.0,  # 마지막 외부 API 실패 시각 (time.monotonic()). 0.0 = 실패 이력 없음
}


def _reset_cache() -> None:
    """인메모리 캐시/백오프 상태를 초기화한다. 테스트 전용 — 운영 코드에서는 호출하지 않는다."""
    _state["price"] = None
    _state["fetched_at"] = 0.0
    _state["last_failure_at"] = 0.0


def _memory_price_if_within(ttl: int) -> int | None:
    price = _state["price"]
    if price is None:
        return None
    if time.monotonic() - _state["fetched_at"] < ttl:
        return price  # type: ignore[return-value]
    return None


def _in_backoff() -> bool:
    return time.monotonic() - _state["last_failure_at"] < BACKOFF_SECONDS


def _remember_success(price: int) -> None:
    _state["price"] = price
    _state["fetched_at"] = time.monotonic()
    _state["last_failure_at"] = 0.0  # 성공했으니 백오프 해제


def _remember_failure() -> None:
    _state["last_failure_at"] = time.monotonic()


def _get_redis_client():
    """Redis 클라이언트를 반환한다. 설정이 없거나 연결에 실패하면 None."""
    if not settings.redis_url:
        return None
    try:
        from app.services.job_queue import get_redis_client
        return get_redis_client()
    except Exception:
        logger.warning("btc_price: Redis 연결 실패 — 캐시 없이 진행", exc_info=True)
        return None


def _fetch_from_coingecko() -> int | None:
    try:
        resp = httpx.get(
            COINGECKO_URL,
            params={"ids": "bitcoin", "vs_currencies": "krw"},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        price = resp.json().get("bitcoin", {}).get("krw")
        if price is None:
            logger.warning("btc_price: CoinGecko 응답에 krw 가격 없음")
            return None
        return int(price)
    except Exception:
        logger.warning("btc_price: CoinGecko 조회 실패", exc_info=True)
        return None


def get_btc_price_krw() -> int | None:
    """현재 BTC/KRW 가격(원 단위 정수)을 반환한다.

    순서: 인메모리(신선) → Redis(신선) → CoinGecko(백오프 중이면 건너뜀)
          → 인메모리(stale) → Redis(stale) → None.
    """
    mem_fresh = _memory_price_if_within(CACHE_TTL)
    if mem_fresh is not None:
        return mem_fresh

    r = _get_redis_client()

    if r is not None:
        try:
            cached = r.get(CACHE_KEY)
            if cached is not None:
                price = int(cached)
                # Redis에서 찾은 신선한 값을 로컬에도 채워, 이후 호출은 인메모리로 처리한다.
                _remember_success(price)
                return price
        except Exception:
            logger.warning("btc_price: 캐시 조회 실패", exc_info=True)

    if _in_backoff():
        logger.info("btc_price: 최근 실패로 백오프 중 — 외부 API 호출 건너뜀")
    else:
        price = _fetch_from_coingecko()
        if price is not None:
            _remember_success(price)
            if r is not None:
                try:
                    r.setex(CACHE_KEY, CACHE_TTL, price)
                    r.setex(STALE_CACHE_KEY, STALE_TTL, price)
                except Exception:
                    logger.warning("btc_price: 캐시 저장 실패", exc_info=True)
            return price
        _remember_failure()

    mem_stale = _memory_price_if_within(STALE_TTL)
    if mem_stale is not None:
        logger.info("btc_price: 인메모리 stale 캐시로 폴백")
        return mem_stale

    if r is not None:
        try:
            stale = r.get(STALE_CACHE_KEY)
            if stale is not None:
                logger.info("btc_price: Redis stale 캐시로 폴백")
                return int(stale)
        except Exception:
            logger.warning("btc_price: stale 캐시 조회 실패", exc_info=True)

    return None
