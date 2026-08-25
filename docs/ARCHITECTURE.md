# Stack Health 시스템 아키텍처

> 운동 쇼츠 공유 + 비트코인 리워드 플랫폼 (https://stackhealth.life)
> 파일 단위 탐색은 `docs/INDEX.md`를 먼저 본다.

## 1. 전체 구성도

```
                        ┌─────────────────────────────┐
  사용자 (웹/모바일앱)   │   nginx (stackhealth.life)   │
 ───────────────────►  │  upstream: blue 8017 / green │
                        │  8018 (blue-green 전환)      │
                        └──────────────┬──────────────┘
                                       ▼
                        ┌─────────────────────────────┐
                        │   FastAPI Backend (Docker)   │
                        │  - REST API (/api 없이 직접) │
                        │  - 정적 SPA 서빙 (frontend   │
                        │    빌드 산출물 fallback)      │
                        └───┬───────┬───────┬─────────┘
                            │       │       │
              ┌─────────────┘       │       └─────────────┐
              ▼                     ▼                     ▼
   ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
   │ PostgreSQL (prod) │  │   Redis 잡 큐    │  │  Cloudflare R2   │
   │ SQLite (dev)      │  │ queue:merge-jobs │  │ (영상/썸네일/    │
   └──────────────────┘  └────────┬─────────┘  │  이미지 저장)    │
                                   ▼            └──────────────────┘
                        ┌──────────────────────┐         ▲
                        │  Video Worker         │─────────┘
                        │  (systemd, ffmpeg)    │  처리 결과 업로드
                        │  병합/인코딩/자막      │
                        └──────────────────────┘

   외부 서비스: Blink Lightning API (BTC 송금) · Google OAuth · Telegram (운영 알림)
```

## 2. 컴포넌트

### Backend — `backend/` (FastAPI + SQLAlchemy + Alembic)

- 단일 FastAPI 앱(`app/main.py`)이 API와 frontend 빌드 정적 파일을 함께 서빙한다.
- 라우터 8개: `auth` `videos` `feed` `admin` `comments` `history` `challenges` `users`
- 계층: `routes/`(HTTP) → `services/`(비즈니스 로직) → `models/`(SQLAlchemy ORM), 입출력은 `schemas/`(Pydantic).
- 인증 3종:
  - 이메일+비밀번호 → JWT (`services/auth.py`)
  - Google OAuth (`services/google_oauth.py`, 선택 — env 미설정 시 비활성)
  - Lightning LNURL-auth (`services/lnauth.py`, `models/lnauth_challenge.py`)
- 어드민: `ADMIN_SECRET_KEY` 헤더 인증. 삭제/ban/정산은 `models/admin_log.py`에 감사 로그.

### Frontend — `frontend/` (React + Vite + TailwindCSS)

- SPA. 라우팅은 `src/App.tsx` (React Router + `RequireAuth` 가드).
- 상태: Zustand(`store/` — auth/theme/ui) + TanStack Query(서버 상태).
- API 호출은 전부 `src/api/client.ts` 경유. 에러 코드는 `ERR_CODE.md`와 동기.
- 업로드 플로우는 단계형 컴포넌트(`pages/upload/StepRecord → StepSelectVideo → StepCaption → StepTagChallenge`).
- 빌드 산출물은 Docker 이미지에 포함되어 backend가 서빙.

### Video Worker — `worker/` (독립 프로세스, systemd)

- backend와 별도로 배포되는 Redis 큐 컨슈머 (`worker.py`).
- 잡 종류: `full_pipeline`(인코딩+썸네일+자막 전체), `merge`(영상+오디오), `image_merge`, `subtitle_extract`.
- ffmpeg 동시 실행 제한: Redis ZSET 기반 **만료 리스 세마포어**(Lua 스크립트) — 워커가 죽어도 TTL 후 슬롯 자동 회수.
- 자막: Whisper 기반 추출 + 환각 필터(compression_ratio, avg_no_speech_prob, chars_per_sec — v0.0.45~46).
- Redis 미설정 시 backend가 직접 ffmpeg fallback 수행 (`services/job_queue.py` 참조).
- 처리 결과는 R2 업로드 + 텔레그램 알림(`notify.py`).

### Mobile — `mobile/` (Flutter)

- 배포된 웹앱을 감싸는 WebView 래퍼 (Android/iOS). GitHub Actions 자동 빌드.

## 3. 핵심 데이터 흐름

### 영상 업로드 → 피드 게시

```
프론트 업로드(UploadPage)
→ POST /videos (R2 presigned 업로드 또는 서버 경유)
→ backend: job_queue.enqueue (Redis "queue:merge-jobs:{env}")
→ worker: dequeue → ffmpeg 처리(병합/인코딩/썸네일/자막) → R2 업로드
→ job status 갱신 (job:* 키, TTL 24h) → 프론트 폴링으로 완료 확인
→ post 생성 → 피드(/feed) 노출
```

### 공유 링크

```
영상별 share_token 발급 (services/share_token.py)
→ /shorts/:shareToken — 비로그인 공개 페이지 (SharedVideoPage)
```

## 4. 데이터 모델 (주요 엔티티)

```
User ─┬─< Video ──< Post ─┬─< PostLike
      │                   ├─< PostView
      │                   └─< Comment
      ├─< Challenge 참여                   (challenge.py)
      └─< LnauthChallenge                 (Lightning 로그인 챌린지)
AdminLog                                  (어드민 행위 감사)
AppLinks                                  (앱 링크/메타)
```

상세 컬럼은 `backend/app/models/` 각 파일. 스키마 변경은 반드시 Alembic 마이그레이션 동반.

## 5. 배포 인프라

| 항목 | 내용 |
|---|---|
| 서버 | Ubuntu 자체 서버 (Railway 미사용) |
| 앱 배포 | Docker multi-stage (frontend build → backend) + blue-green |
| 슬롯 | blue=8017 / green=8018, 평상시 한 슬롯만 가동 |
| 전환 | `scripts/deploy.sh` Step 7이 `/etc/nginx/conf.d/stackhealth-upstream.conf` 직접 갱신 후 reload |
| 워커 | systemd `stackhealth-worker.service`, `worker/deploy.sh` 별도 배포 |
| DB | PostgreSQL (양 슬롯 공유) |

> **주의**: repo의 `nginx/upstream.conf`는 참조용. 실제 nginx는 `/etc/nginx/conf.d/stackhealth-upstream.conf`만 읽는다. 장애 이력 포함 상세는 `CLAUDE.md`.

## 6. 환경변수 (요약)

| 그룹 | 키 | 비고 |
|---|---|---|
| DB | `DATABASE_URL` | dev=SQLite, prod=PostgreSQL |
| 인증 | `SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT |
| 스토리지 | `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`, `R2_PUBLIC_URL` | Cloudflare R2 |
| 어드민 | `ADMIN_SECRET_KEY` | 헤더 인증 |
| 리워드 | `BLINK_API_KEY` | 선택 — 미설정 시 수동 송금 |
| 큐 | `REDIS_URL` | 선택 — 미설정 시 backend 직접 ffmpeg |
| OAuth | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | 선택 |
| 앱 | `ENVIRONMENT`, `PORT`, `APP_BASE_URL`, `VITE_APP_BASE_URL` | |

전체 목록·설명: `.env.example`, `backend/ENV_VARS.md`.

## 7. 검증 명령

| 대상 | 명령 |
|---|---|
| Backend 테스트 | `cd backend && .venv/bin/pytest -q` |
| Frontend 빌드 | `cd frontend && npm run build` |
| Frontend 유닛 | `cd frontend && npm test` (Vitest) |
| E2E | `cd frontend && npx playwright test` (`e2e/*.spec.ts`) |
| 전체 | `bash scripts/test.sh` / 린트만 `bash scripts/test.sh lint` |
