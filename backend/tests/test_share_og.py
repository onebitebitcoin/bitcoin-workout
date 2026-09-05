"""공유 링크(/shorts/{token}) OG 페이지 회귀 테스트.

카카오톡 인앱 브라우저 UA 를 크롤러로 잡으면 OG 페이지가 같은 URL 로
자기 자신을 리다이렉트해 무한 루프가 되고, 사용자는 링크가 열리지 않는다.
"""

from __future__ import annotations

from app.main import _OG_BYPASS_PARAM, _is_crawler, _og_html

KAKAO_INAPP_UA = (
    "Mozilla/5.0 (Linux; Android 13; SM-S918N) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Mobile Safari/537.36 KAKAOTALK 10.4.3"
)
KAKAO_INAPP_IOS_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Mobile/15E148 KAKAOTALK 10.4.3"
)


class _FakeRequest:
    def __init__(self, ua: str) -> None:
        self.headers = {"user-agent": ua}


def test_kakaotalk_inapp_browser_is_not_treated_as_crawler():
    assert _is_crawler(_FakeRequest(KAKAO_INAPP_UA)) is False
    assert _is_crawler(_FakeRequest(KAKAO_INAPP_IOS_UA)) is False


def test_kakaotalk_scraper_is_still_treated_as_crawler():
    assert _is_crawler(_FakeRequest("kakaotalk-scrap/1.0")) is True


def test_known_scrapers_are_still_treated_as_crawlers():
    for ua in ("Twitterbot/1.0", "facebookexternalhit/1.1", "TelegramBot (like TwitterBot)", "Googlebot/2.1"):
        assert _is_crawler(_FakeRequest(ua)) is True


def test_plain_browser_is_not_a_crawler():
    assert _is_crawler(_FakeRequest("Mozilla/5.0 (iPhone) Safari/605.1.15")) is False


def test_og_html_redirects_with_loop_guard_not_to_itself():
    page_url = "https://example.com/shorts/abc123"
    html = _og_html(
        "제목", "설명", "https://cdn/i.jpg", page_url, None, f"{page_url}?{_OG_BYPASS_PARAM}=1"
    )
    # og:url 은 정규 URL 그대로 유지한다
    assert f'property="og:url" content="{page_url}"' in html
    # 사람에게 되돌려 보내는 링크에는 루프 차단 표식이 붙는다
    assert f"{page_url}?{_OG_BYPASS_PARAM}=1" in html
    assert f'window.location.replace("{page_url}")' not in html
    # JS 가 막힌 환경을 위한 링크 폴백
    assert "<a href=" in html
