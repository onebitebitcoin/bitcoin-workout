# 배포 노트 — Orange Story 리브랜딩 (v0.19.1 → v0.20.0)

> 서버에서 `bash scripts/deploy.sh`를 돌리기 **전에** 읽는다.
> 이 배포는 운영보다 커밋 15개 앞서 있고 미적용 마이그레이션이 3개다. 그중 하나가
> 파괴적(`reward_points` DROP)이라 평소 배포와 위험도가 다르다.

## 이번 배포에 실리는 것

운영은 `dfb2fdd`(v0.19.1). 그 뒤로 쌓인 것:

| 갈래 | 내용 |
|---|---|
| 브랜드 | Stack Health → Bitcoiners → **Orange Story**, 팔레트·로고·타이포 교체 |
| 도메인 | 코드가 `story.onebitebitcoin.com` 기준으로 바뀜 (canonical·OG·sitemap) |
| 기능 | 오렌지 나무(`GET /users/me/tree`), 게시물 시세 박제, CoinGecko 연동 |
| 정리 | 땀방울 점수 체계 제거, 카테고리 리맵, 타임존 배관 제거 |

미적용 마이그레이션 3개 (`alembic upgrade head`가 한 번에 실행한다):

| 리비전 | 내용 | 위험 |
|---|---|---|
| `c7d8e9f0a1b2` | `reward_points` **DROP** | **높음** — 아래 1장 |
| `004aa221ea8d` | 업로드 카테고리 리맵 | 낮음 (행 단위 UPDATE, 시간만 걸림) |
| `cbb7d21fb47c` | `posts.btc_price_krw` ADD COLUMN (nullable) | 없음 |

---

## 1. 가장 큰 위험 — `reward_points` DROP과 blue-green 창

`deploy.sh`는 4단계에서 마이그레이션을 돌리고 7단계에서야 구 슬롯을 죽인다. 그
사이 **구 슬롯은 여전히 nginx가 트래픽을 보내는 대상**이고, 두 슬롯은 같은 DB를
본다. 운영 코드(`dfb2fdd`)는 `reward_points`를 8개 파일에서 참조한다.

즉 테이블이 사라진 순간부터 구 슬롯이 죽을 때까지, 업로드·댓글·관리자 기능이
500으로 떨어진다. 특히 업로드는 ffmpeg 처리를 다 끝낸 뒤 마지막 저장에서 깨져
**사용자가 3분을 기다리고 결과물을 잃는다.**

깨지는 경로 전체 목록과 증상, 완화 방안 4가지(A~D)는
**`docs/DOMAIN-CUTOVER.md` 1-4장**에 이미 정리돼 있다. 배포 전에 그 장을 읽고
방안을 하나 정한다. 요약만 옮기면:

- **A. 저트래픽 시간대(새벽)에 감수** — 지금 바로 가능. 창은 남고 확률만 낮춘다
- **B. 코드 먼저, DROP은 다음 배포** — 커밋을 쪼개야 하고, 유저 삭제 FK 문제를
  같이 풀어야 한다(실측 확인됨)
- **C. DROP 대신 rename** — 되돌릴 여지는 생기지만 창 자체는 그대로
- **D. `deploy.sh`에서 마이그레이션을 7단계 뒤로** — 창을 구조적으로 없앤다.
  스크립트 수정 필요

> 창의 길이는 최선이어도 수십 초, 리맵 대상이 많으면 1분을 넘길 수 있다.

## 2. 두 번째 창 — 새 프론트 + 구 백엔드

3단계(프론트 빌드)가 끝나는 순간부터 문제가 시작된다. 빌드 산출물은
`backend/static/`으로 가고 **두 슬롯이 이 디렉토리를 공유**한다. 슬롯 전환(7단계)
전인데도 구 슬롯이 이미 새 프론트를 서빙한다.

| 증상 | 왜 |
|---|---|
| 프로필의 나무 카드가 안 보임 | 새 프론트가 `GET /users/me/tree`를 부르는데 구 백엔드에 없다(404). **의도적으로 조용히 숨기게 만들어서 화면은 정상** |
| 캘린더 날짜가 하루 밀려 보일 수 있음 | 새 프론트는 `?timezone=`을 안 보내고, 구 백엔드는 없으면 UTC로 계산한다. 한국시간 오전 9시 이전 기록이 전날 칸에 찍힌다 |
| 댓글 일일 제한이 UTC 자정 기준 | `X-Client-Timezone` 헤더가 사라져서. 같은 이유 |

전부 7단계 이후 자동으로 해소된다. 데이터가 잘못 저장되지는 않는다 — 표시와
카운트 기준만 잠깐 어긋난다.

## 3. 도메인 — 순서를 지켜야 공유 카드가 안 깨진다

코드는 이미 `story.onebitebitcoin.com`을 가리킨다(canonical, `og:image`, sitemap).
DNS·인증서가 없는 상태로 배포하면 **SNS 공유 카드 이미지가 죽은 URL을 가리켜
깨진다.**

```
story DNS + 인증서 먼저  →  그 다음 코드 배포
```

`docs/DOMAIN-CUTOVER.md`의 Step 1~4를 먼저 끝낸다.

### 기존 도메인을 살려두는 구성 (301 없이 병행)

`stackhealth.life`를 당분간 유지하려면 Step 5(301 전환)를 **건너뛰고** 이렇게 둔다:

```
nginx server_name: stackhealth.life  story.onebitebitcoin.com   (둘 다)
인증서:            양쪽 다
.env:              APP_URL = APP_BASE_URL = https://story.onebitebitcoin.com
```

동작:

- **도메인을 따라가는 것** — 프론트의 공유·초대 링크는 `window.location.origin`을
  쓴다. `stackhealth.life`로 들어온 사용자는 그 도메인 링크를 만든다. 문제없다.
- **한쪽으로 쏠리는 것** — `APP_URL`/`APP_BASE_URL`은 값이 하나뿐이라, 여기에
  묶인 것들은 전부 새 도메인으로 간다:

  | 값 | 쓰는 곳 |
  |---|---|
  | `APP_URL` | Google OAuth `redirect_uri` (`services/google_oauth.py:49`) |
  | `APP_BASE_URL` | Google 로그인 완료 리다이렉트, LNURL-auth 콜백, 크롤러용 공유 카드의 `og:url`·`og:image` |

  결과: `stackhealth.life`에서 Google 로그인하면 **로그인이 끝나는 순간
  `story...`로 넘어간다.** 로그인 자체는 정상 동작하고 도메인만 바뀐다.

이 구성이면 기존 링크·북마크·설치된 앱이 계속 살아있고, 로그인하는 사용자만
자연스럽게 새 도메인으로 옮겨간다. 트래픽이 넘어간 걸 확인한 뒤 301을 걸면 완전
전환이다.

> **양쪽에서 각자 도메인으로 로그인이 끝나게** 하려면 요청 `Host`를 보고
> `redirect_uri`를 동적으로 만들어야 한다. Host 헤더를 신뢰하는 구조라 허용 도메인
> 화이트리스트가 필요하고, 전환기에만 쓸 코드치고 위험이 크다. 권하지 않는다.

### Google OAuth 재등록 (빠뜨리면 로그인이 죽는다)

`APP_URL`을 바꿨다면 Google Cloud Console에 이 URI를 **추가**한다:

```
https://story.onebitebitcoin.com/api/v1/auth/google/callback
```

기존 `stackhealth.life` 항목은 남겨둔다 — 캐시된 옛 링크의 안전망이다.
절차와 검증은 `docs/DOMAIN-CUTOVER.md` 3장.

## 4. 새로 생긴 외부 의존성 — CoinGecko

이 서비스에 시세를 가져오는 경로가 없었다. 오렌지 나무의 열매가 이걸 쓴다.

- API 키는 필요 없다. 무료 티어를 그대로 쓴다.
- **`REDIS_URL`이 설정돼 있는지 확인한다.** 캐시가 두 겹(인메모리 + Redis)인데,
  Redis가 없으면 프로세스마다 따로 캐시를 들고 있어 외부 호출이 늘어난다.
  인메모리 계층만으로도 429는 막지만, Redis가 있으면 슬롯·워커가 값을 공유한다.
- 실패해도 서비스는 죽지 않는다 — 나무만 그리고 열매 UI를 숨긴다. 업로드도
  가격을 못 구하면 `NULL`로 두고 정상 진행한다.
- 방화벽에서 아웃바운드 HTTPS(`api.coingecko.com`)가 막혀 있지 않은지만 본다.

## 5. 영구적으로 바뀌는 동작 — 날짜 경계

날짜 경계가 **Asia/Seoul 고정**으로 바뀐다(전에는 클라이언트가 보낸 타임존).

- 조회수 일일 중복 제거 기준이 UTC 자정 → 한국 자정으로 이동한다. 배포 당일
  하루만 카운트 구간이 겹치거나 벌어진다.
- 해외 접속자는 이제 한국 자정 기준으로 날짜가 끊긴다. 주 사용자가 한국이라
  의도한 선택이다(`SPEC.md` 2장).

## 6. 워커

`worker/tasks/full_pipeline.py`, `full_pipeline_multi.py`가 바뀌었다(가격 박제).
`deploy.sh`가 `WORKER_INSTANCES`를 읽어 `stack-health-worker@1..N`을 자동으로
재시작하므로 **따로 할 일은 없다.**

`worker/DEPLOY.md`와 `worker/deploy.sh`는 이번에 `archive-meta/worker-opt/`로
옮겼다 — 실행된 적 없는 `/opt` 전용서버 경로였다. 워커 전용 배포 스크립트는 없다.

## 7. 배포 직후 확인

```bash
# 서비스가 살아있나
curl -s https://story.onebitebitcoin.com/health
curl -Ik https://stackhealth.life/          # 병행 운영이면 이것도 200

# 새 엔드포인트 (로그인 토큰 필요)
curl -s https://story.onebitebitcoin.com/api/v1/users/me/tree -H "Authorization: Bearer <token>"
#   fruit.available:false 여도 정상 — 시세만 못 가져온 것이다

# 공유 카드가 새 도메인을 가리키나
curl -s https://story.onebitebitcoin.com/ | grep -E 'og:image|canonical'

# 시세 조회가 되나 (백엔드 로그)
journalctl --user -u stack-health-app-blue -n 50 | grep btc_price
```

브라우저로는 이 둘을 본다 — curl로 대체되지 않는다:

- Google 로그인을 끝까지 (redirect_uri 불일치는 브라우저에서만 드러난다)
- 프로필 화면의 나무 카드 (단계·진행 막대·열매)

## 8. 롤백

| 문제 | 되돌리기 |
|---|---|
| 배포 자체가 실패 | `deploy.sh`가 헬스체크 실패 시 새 슬롯을 정리하고 구 슬롯을 유지한다. nginx는 전환되지 않는다 |
| 전환 후 이상 | `sudo /usr/local/bin/stackhealth-nginx-switch <구 슬롯 포트>` 로 되돌린다 (blue=8017 / green=8018). **단 마이그레이션은 되돌아가지 않는다** — 구 코드는 `reward_points`가 없어 1장의 증상을 그대로 겪는다 |
| Google 로그인 실패 | `.env`의 `APP_URL`을 이전 도메인으로 되돌리고 재배포 |
| 시세가 계속 안 나옴 | 기능 문제 아님. 나무는 정상 동작한다. `journalctl`에서 429/타임아웃 확인 |

> 마이그레이션 롤백(`alembic downgrade`)은 `reward_points`의 **데이터를 되살리지
> 못한다**. DROP 전에 백업을 뜰지는 1장의 방안을 정할 때 같이 판단한다.

## 9. 체크리스트

- [ ] `docs/DOMAIN-CUTOVER.md` 1-4장을 읽고 완화 방안(A~D) 하나를 정했다
- [ ] `reward_points` 백업 여부를 정했다
- [ ] `story.onebitebitcoin.com` DNS A레코드 + 인증서 (Step 1~2)
- [ ] nginx `server_name`에 두 도메인, `nginx -t` 통과 (Step 3)
- [ ] 새 도메인 단독 접속 검증 (Step 4)
- [ ] `.env`의 `APP_URL`/`APP_BASE_URL` 갱신
- [ ] Google Cloud Console에 새 `redirect_uri` 추가
- [ ] `REDIS_URL` 설정 확인, `api.coingecko.com` 아웃바운드 확인
- [ ] 저트래픽 시간대인지 확인 (A안을 골랐다면)
- [ ] `bash scripts/deploy.sh`
- [ ] 7장의 확인 항목 + 브라우저로 Google 로그인·나무 카드
