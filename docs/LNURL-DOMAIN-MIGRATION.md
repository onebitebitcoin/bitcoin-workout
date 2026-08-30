# LNURL-auth 도메인 고정 — 원인과 마이그레이션

> 2026-08-30 작성. 도메인 전환(`stackhealth.life` → `story.onebitebitcoin.com`) 직후
> "라이트닝 로그인이 재사용되지 않는다"는 사용자 문의에서 출발했다.

## 한 줄 요약

**라이트닝 사용자의 신원은 도메인에 묶여 있다.** 그래서 서비스 도메인을 옮겨도 LNURL 이
담는 도메인은 `stackhealth.life` 로 고정한다. `LNURL_BASE_URL` 이 그 고정값이다.

## 왜 그런가 — LUD-04

지갑은 서비스마다 다른 키로 로그인한다. 그 키를 이렇게 만든다.

```
hashingKey = BIP32(masterKey, "m/138'/0")
domainHash = HMAC-SHA256(hashingKey, FQDN)        ← LNURL 의 도메인이 입력으로 들어간다
linkingKey = BIP32(masterKey, "m/138'/<domainHash 앞 16바이트를 uint32 4개로>")
```

규격은 **FQDN 전체**(base domain 아님)를 쓰라고 못박는다. 도메인이 한 글자라도 다르면
HMAC 입력이 달라져 파생 경로가 통째로 갈리고, 같은 지갑이 **관계 없는 다른 공개키**를
내놓는다. 서버에는 그 둘을 이어붙일 방법이 없다 — 매핑은 지갑 시드 안에만 있다.

## 증상이 왜 눈에 안 띄었나

`backend/app/routes/auth.py` 의 로그인 조회는 이렇다.

```python
user = db.query(User).filter(User.oauth_sub == key, User.oauth_provider == "lnauth").first()
if user is None:
    ...  # 신규 가입 분기
```

공개키가 달라지면 조회가 빗나가고 **에러 없이 빈 새 계정이 생긴다.** 사용자는
"로그인 실패"가 아니라 "내 기록이 전부 사라진 낯선 계정"을 본다. 로그·모니터링에는
정상 가입으로 찍혀서 알림이 울리지 않는다.

## 실제 피해 (2026-08-30 조사)

| 항목 | 값 |
|---|---|
| 전환 이전 lnauth 계정 | 24 |
| 그 중 게시물 보유 | 10 |
| 전환 이후 생긴 중복 계정 | 4 (`133`, `134`, `135`, `136`) |
| 그 중 콘텐츠 있는 계정 | `134 데이이` — 게시물 1, 영상 1 |

`134 데이이` 는 `70 데이`(2026-05-31 가입)와 동일인으로 추정된다. 원래 닉네임이 이미
점유돼 있어 글자를 덧붙인 정황이다.

구 도메인이 맞다는 근거는 nginx 접근 로그다 — 전환 이전 lnauth 로그인 15건의 리퍼러가
전부 `https://stackhealth.life/login/lightning` 이었다.

## 구글 로그인과 다른 점

`DEPLOY-NOTES-orange-story.md` 의 "기존 사용자는 새 도메인에서 한 번 더 로그인해야
한다"는 **구글에만** 해당한다. 구글의 `sub` 는 도메인과 무관해서 계정은 그대로고
세션만 끊긴다. 라이트닝은 신원 자체가 바뀌므로 성격이 다르고 더 나쁘다.

## 적용한 구조

| 설정 | 쓰이는 곳 | 도메인 전환 시 |
|---|---|---|
| `APP_URL` | 구글 OAuth `redirect_uri` 베이스 | 새 도메인으로 **따라간다** |
| `APP_BASE_URL` | 구글 로그인 완료 리다이렉트, 공유 카드 `og:url` | 새 도메인으로 **따라간다** |
| `LNURL_BASE_URL` | LNURL QR, LNURL 콜백 | **고정한다 — 절대 바꾸지 않는다** |

- `backend/app/config.py` — `lnurl_base_url` 필드와 `lnurl_origin` 프로퍼티.
  비어 있으면 `app_base_url` 을 따르므로 로컬·신규 배포는 기존 동작 그대로다.
- `backend/app/services/lnauth.py` — QR 에 박히는 URL
- `backend/app/routes/auth.py` — 먼저 탐색 요청을 보내는 지갑에 돌려주는 `callback`
- `backend/tests/test_lnauth_domain.py` — 이 불변식의 회귀 테스트

서명 검증(`verify_signature`)은 도메인을 보지 않는다. 구 도메인으로 파생한 키를
신 도메인 백엔드가 받아도 정상 통과한다.

## nginx — 구 도메인의 예외 경로

`stackhealth.life` 는 전체가 301 이지만 `/api/v1/auth/lnauth` 만 백엔드로 직접 넘긴다.
리다이렉트를 따르지 않는 지갑이 있어 301 로 대신할 수 없다.

```nginx
location ^~ /api/v1/auth/lnauth {
    proxy_pass http://stackhealth_app;
    ...
}
location / {
    return 301 https://story.onebitebitcoin.com$request_uri;
}
```

파일: `/etc/nginx/sites-available/stackhealth.life` (sites-enabled 는 심링크).

## 로그인 화면의 도메인 선택 (신규 사용자용)

서버는 QR 을 만드는 시점에 상대가 누구인지 알 수 없다 — LNURL-auth 는 익명으로 QR 을
뿌리고 서명이 돌아와야 신원이 확정되기 때문이다. 그래서 자동 감지는 불가능하고,
**사용자가 직접 고른다.**

| 화면 선택 | 요청 | LNURL 도메인 | 결과 |
|---|---|---|---|
| 기존 계정이 있어요 | `?domain=legacy` (기본값) | `LNURL_BASE_URL` = stackhealth.life | 원래 계정으로 로그인 |
| 처음 왔어요 | `?domain=current` | `APP_BASE_URL` = story.onebitebitcoin.com | 신 도메인 신원으로 새 계정 |

- 기본값이 `legacy` 인 것이 안전장치다. 파라미터를 모르는 호출자 — **이미 설치된 모바일
  앱** 포함 — 는 기존 동작을 그대로 유지한다. 모르는 값이 와도 `legacy` 로 떨어진다.
- 콜백 응답의 `callback` 은 요청이 들어온 도메인을 그대로 돌려준다(`_callback_origin`).
  신원이 그 도메인으로 파생됐기 때문이다. `Host` 는 조작 가능하므로 우리가 실제로
  서비스하는 두 도메인만 허용한다. (참고: 실측한 지갑 호출 21건은 전부 `sig`·`key` 를
  바로 동봉하는 1단계였고 probe 는 0건이었다 — 이 필드는 사실상 쓰이지 않는다.)

**남아 있는 위험**: 기존 사용자가 "처음 왔어요"를 고르면 이 문서가 설명하는 사고가
그대로 재발한다 — 빈 새 계정이 조용히 생긴다. 사용자는 자기가 어느 쪽인지 모를 수 있다
(오래전 가입했거나 지갑을 바꿨거나). 화면에서는 신규 쪽 QR 위에 경고 문구를 띄워
되돌아갈 길을 열어두는 것으로 막는다. 구조적으로 없애려면 아래 "남은 과제"의 다중 키
설계가 필요하다.

## 그래서 계속 지켜야 하는 것

- **`stackhealth.life` DNS 와 Let's Encrypt 인증서를 계속 유지한다.** 이 도메인이
  죽으면 라이트닝 사용자 전원이 계정을 잃는다. certbot 자동 갱신 대상에 남아 있는지
  주기적으로 확인한다.
- Cloudflare 존 설정에서 이 경로에 봇 차단·챌린지를 걸지 않는다. 지갑은 브라우저가
  아니라 `AHC/1.0` 같은 UA 로 들어온다.
- 배포 시 `.env` 의 `LNURL_BASE_URL` 이 유지되는지 확인한다.

## 남은 과제 — 구 도메인 은퇴 경로 (이번 범위 밖)

지금 구조는 `stackhealth.life` 에 영구히 묶인다. 풀려면 계정 하나가 공개키 여러 개를
가질 수 있어야 한다.

1. `user_lnauth_keys` 테이블 신설 (user 1 : N pubkey), 로그인 조회를 이 테이블 기준으로
2. 로그인 상태에서 신 도메인 LNURL 을 한 번 더 스캔해 새 키를 계정에 추가 연결
3. 대부분이 두 키를 갖게 되면 `LNURL_BASE_URL` 을 새 도메인으로 옮기고 구 도메인 은퇴

이 작업 없이 도메인을 다시 옮기면 같은 사고가 반복된다.
