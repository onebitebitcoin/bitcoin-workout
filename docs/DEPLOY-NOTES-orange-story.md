# 배포 노트 — Orange Story 리브랜딩 (v0.19.1 → v0.20.0)

> 서버에서 `bash scripts/deploy.sh`를 돌리기 **전에** 읽는다.
> 이 배포는 운영보다 커밋 15개 앞서 있고 미적용 마이그레이션이 3개다. 그중 하나가
> 파괴적(`reward_points` DROP)이라 평소 배포와 위험도가 다르다.
>
> 그 위험은 **expand/contract 방식으로 제거했다**(1장). 남은 준비는 도메인 순서와
> Google OAuth 재등록이다.

## 이번 배포에 실리는 것

운영은 `dfb2fdd`(v0.19.1). 그 뒤로 쌓인 것:

| 갈래 | 내용 |
|---|---|
| 브랜드 | Stack Health → Bitcoiners → **Orange Story**, 팔레트·로고·타이포 교체 |
| 도메인 | 코드가 `story.onebitebitcoin.com` 기준으로 바뀜 (canonical·OG·sitemap) |
| 기능 | 오렌지 나무(`GET /users/me/tree`), 게시물 시세 박제, CoinGecko 연동 |
| 정리 | 땀방울 점수 체계 제거, 카테고리 리맵, 타임존 배관 제거 |

미적용 마이그레이션 3개:

실행 순서는 아래와 같이 재배열했다(1장 참고). `expand`는 구 슬롯이 살아있는 채로
올려도 안전한 것, `contract`는 구 슬롯이 죽은 뒤에만 안전한 것이다.

| 순서 | 리비전 | 내용 | 단계 |
|---|---|---|---|
| 1 | `004aa221ea8d` | 업로드 카테고리 리맵 | expand — 데이터만 바꾼다 |
| 2 | `cbb7d21fb47c` | `posts.btc_price_krw` ADD COLUMN | expand — 구 코드는 이 컬럼을 모른다 |
| 3 | `c7d8e9f0a1b2` | `reward_points` **DROP** | **contract** — 구 코드가 8개 파일에서 쓴다 |

---

## 1. `reward_points` DROP — expand/contract 로 창을 없앴다

### 원래 무엇이 문제였나

`deploy.sh`는 4단계에서 마이그레이션을 돌리고 7단계에서야 구 슬롯을 죽였다. 그
사이 **구 슬롯은 여전히 nginx 트래픽을 받는 대상**이고 두 슬롯은 같은 DB 를 본다.
운영 코드(`dfb2fdd`)는 `reward_points`를 8개 파일에서 참조한다.

즉 테이블이 사라진 순간부터 구 슬롯이 죽을 때까지 업로드·댓글·관리자 기능이 500 이
됐다. 업로드는 ffmpeg 처리를 다 끝낸 뒤 마지막 저장에서 깨져 **사용자가 3분을
기다리고 결과물을 잃는다.** 깨지는 경로 전체 목록은 `docs/DOMAIN-CUTOVER.md` 1-4장.

### 어떻게 없앴나

마이그레이션을 성격에 따라 둘로 갈랐다.

| | 무엇 | 언제 |
|---|---|---|
| **expand** | 구 코드가 봐도 안전한 것 (ADD COLUMN, 데이터 이동) | 슬롯 기동 **전** (Step 4) |
| **contract** | 구 코드가 쓰던 것을 없애는 것 (DROP) | 구 슬롯 종료 **후** (Step 7) |

두 가지를 바꿨다.

1. **마이그레이션 체인 재배열** — DROP 을 맨 뒤로 옮겼다. 원래는 DROP 이 중간에
   있어서 `btc_price_krw`(새 코드에 필수)까지 올리려면 DROP 을 반드시 거쳐야 했다.

   ```
   전: d953acd3a18d → c7d8e9f0a1b2(DROP) → 004aa221ea8d → cbb7d21fb47c
   후: d953acd3a18d → 004aa221ea8d → cbb7d21fb47c → c7d8e9f0a1b2(DROP)
   ```

2. **`scripts/deploy.sh` 2단계 마이그레이션** — `backend/alembic/EXPAND_TARGET`
   파일이 있으면 Step 4 에서 그 리비전까지만 올리고, 나머지는 구 슬롯이 죽은 뒤
   Step 7 에서 올린다. 파일이 없으면 지금까지처럼 head 까지 한 번에 올린다
   (파괴적 변경이 없는 평소 배포는 동작이 그대로다).

> **주의**: 마이그레이션을 그냥 전부 뒤로 미루면 안 된다. 새 코드는
> `posts.btc_price_krw` 를 SELECT·INSERT 하므로, 그 컬럼 없이 새 슬롯이 뜨면
> 피드·프로필이 전부 깨진다. 확장은 앞, 수축은 뒤 — 이 구분이 핵심이다.

### 실측으로 확인한 것

SQLite 임시 DB 로 운영과 같은 시작점(`d953acd3a18d`)을 만들고 단계별로 돌렸다.

| 시점 | `reward_points` | `btc_price_krw` | 구 코드(v0.19.1) | 새 코드 |
|---|---|---|---|---|
| expand 후 | 있음 | 있음 | `/feed` 200, `/rewards/summary` 도달 | `/feed` 200 |
| contract 후 | 없음 | 있음 | — (이미 종료됨) | 정상 |

대조군으로 **contract 까지 올린 DB 에 구 코드를 붙여봤더니** 실제로
`sqlite3.OperationalError: no such table: reward_points` 가 났다 — 기존 방식이
만들던 바로 그 장애다. expand 시점 스키마에서는 양쪽 코드가 모두 정상이었다.

### 배포 후 할 일

`backend/alembic/EXPAND_TARGET` 을 **지운다.** 다음 배포부터는 다시 head 까지 한 번에
올린다. 파일을 남겨두면 그 리비전에서 멈춰 새 마이그레이션이 적용되지 않는다.

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

### 기존 사용자는 새 도메인에서 한 번 더 로그인해야 한다 (문의가 들어올 지점)

계정은 하나다. DB의 `users` 행은 도메인과 무관하므로 영상·기록·나무·챌린지가
전부 그대로 나온다. **다만 세션은 도메인마다 따로다.**

`store/auth.ts`가 zustand `persist`(기본 저장소 `localStorage`)를 쓰는데,
localStorage 는 오리진별로 격리된다. 게다가 `stackhealth.life`와
`onebitebitcoin.com`은 상위 도메인이 달라 쿠키 공유도 불가능하다 — 브라우저
정책이라 우회할 방법이 없다.

정확히 말하면 "로그아웃당하는" 게 아니다:

- `stackhealth.life` 세션은 **끊기지 않는다.** 그 주소를 계속 쓰면 로그인 상태 유지
- `story.onebitebitcoin.com`은 처음 가는 곳이라 로그인 화면이 뜬다
- 로그인만 하면 데이터는 그대로다. 잃는 것은 없고 한 번의 번거로움만 있다

**언제 겪는가**는 배포 방식이 정한다. 301 없이 병행 운영하면 사용자가 스스로
새 주소로 옮길 때만 겪는다(Google 로그인을 누르는 사람은 그 순간 자동으로 새
도메인에 로그인되니 오히려 매끄럽다). 301 을 걸면 전원이 한꺼번에 겪는다.

> 우회하려면 구 도메인이 토큰을 URL 에 실어 새 도메인으로 넘기는 브리지가
> 필요한데, 인증 토큰이 URL(접근 로그·리퍼러)에 남는다. 전환기에만 쓸 코드치고
> 위험이 커서 권하지 않는다.

**모바일 앱은 별개다.** 이미 설치된 앱은 빌드 시점 값(`stackhealth.life`)을 계속
열기 때문에 아무 변화가 없다. 스토어 업데이트를 받아야 새 도메인을 열고, 그때
한 번 로그인이 필요하다.

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
| 전환 후 이상 | `sudo /usr/local/bin/stackhealth-nginx-switch <구 슬롯 포트>` 로 되돌린다 (blue=8017 / green=8018). **단 contract 가 이미 실행됐다면** 구 코드는 `reward_points`가 없어 1장의 증상을 그대로 겪는다. 롤백 가능성을 남기려면 contract 전에 판단해야 한다 |
| Google 로그인 실패 | `.env`의 `APP_URL`을 이전 도메인으로 되돌리고 재배포 |
| 시세가 계속 안 나옴 | 기능 문제 아님. 나무는 정상 동작한다. `journalctl`에서 429/타임아웃 확인 |

> 마이그레이션 롤백(`alembic downgrade`)은 `reward_points`의 **데이터를 되살리지
> 못한다**. DROP 전에 백업을 뜰지는 1장의 방안을 정할 때 같이 판단한다.

## 9. 체크리스트

- [ ] `backend/alembic/EXPAND_TARGET` 파일이 있다 (없으면 head 까지 한 번에 올라가 1장의 창이 생긴다)
- [ ] `reward_points` 백업 여부를 정했다 (contract 로 미뤄도 결국 지워진다)
- [ ] `story.onebitebitcoin.com` DNS A레코드 + 인증서 (Step 1~2)
- [ ] nginx `server_name`에 두 도메인, `nginx -t` 통과 (Step 3)
- [ ] 새 도메인 단독 접속 검증 (Step 4)
- [ ] `.env`의 `APP_URL`/`APP_BASE_URL` 갱신
- [ ] Google Cloud Console에 새 `redirect_uri` 추가
- [ ] `REDIS_URL` 설정 확인, `api.coingecko.com` 아웃바운드 확인
- [ ] `bash scripts/deploy.sh`
- [ ] 7장의 확인 항목 + 브라우저로 Google 로그인·나무 카드
- [ ] 배포 후 `backend/alembic/EXPAND_TARGET` 삭제 + 커밋 (남기면 다음 배포가 그 리비전에서 멈춘다)
