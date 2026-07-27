# 프로젝트 탐색 인덱스 (PROJECT INDEX)

> **목적**: 파일 탐색 전에 이 문서를 먼저 읽고 정확한 위치로 바로 이동한다. 불필요한 `ls`/`grep`/디렉토리 순회를 줄여 토큰을 절약한다.
> **갱신 규칙**: 디렉토리/파일 구조가 바뀌면 이 문서도 함께 갱신한다.
> 아키텍처 상세는 `docs/ARCHITECTURE.md` 참조.

## 한눈에 보기

```
stack_health/
├── backend/    FastAPI API 서버 (Python + SQLAlchemy + Alembic)
├── frontend/   React SPA (Vite + TailwindCSS + Zustand + TanStack Query)
├── worker/     Redis 큐 기반 ffmpeg 비디오 처리 워커 (별도 systemd 서비스)
├── mobile/     Flutter WebView 래퍼 앱 (Android/iOS)
├── scripts/    설치/개발/테스트/배포 스크립트
├── docs/       비전·스펙·아키텍처 문서
└── meetings/   multi-agent 토론 회의록 (meetings/INDEX.md)
```

## 작업 유형 → 봐야 할 파일

| 하려는 작업 | 먼저 볼 파일 |
|---|---|
| API 엔드포인트 추가/수정 | `backend/app/routes/<도메인>.py` + `backend/app/schemas/` + `backend/tests/test_<도메인>.py` |
| DB 스키마 변경 | `backend/app/models/<도메인>.py` → `backend/alembic/` 마이그레이션 |
| 인증 (JWT/Google/Lightning) | `backend/app/services/auth.py`, `google_oauth.py`, `lnauth.py` + `backend/app/routes/auth.py` |
| 비트코인 리워드/정산 | `backend/app/services/reward.py` + `backend/app/routes/rewards.py` (Blink Lightning API) |
| 영상 업로드/스토리지 | `backend/app/routes/videos.py` + `backend/app/services/r2.py` (Cloudflare R2) |
| 영상 인코딩/병합/자막 처리 | `worker/tasks/full_pipeline.py`(단일), `full_pipeline_multi.py`(다중 미디어), `compose.py`(영상+이미지 concat), `merge.py`, `subtitle_extract.py` + `backend/app/services/job_queue.py` (Redis 큐 enqueue) |
| 영상 필터 (카툰·운동열·발자국) | `backend/app/services/cartoon.py`(카툰 렌더러) + `backend/app/services/muscle_heat.py`(포즈 기반 근육 히트맵, mediapipe; `preset_for_exercise` 운동별 프리셋) + `backend/app/services/exercise_classify.py`(Gemini 운동 종목 분류) + `backend/app/services/motion_fx.py`(옵티컬 플로우 기반 발자국 리듬 효과, 포즈 불필요) + `POST /videos/filter-preview`(1프레임 미리보기, `video_filter=cartoon\|heat\|cartoon_heat\|footsteps`) + `worker/tasks/full_pipeline_multi.py`(`_apply_video_filter`; heat 계열만 classify) + `frontend/src/pages/upload/StepMedia.tsx`(효과 선택 라디오 UI) + `frontend/src/utils/videoFilter.ts`(옵션 목록·타입) |
| 다중 미디어 업로드 (영상≤1+이미지≤5) | `frontend/src/pages/upload/Step{Media,Subtitle,Meta}.tsx` → `POST /videos/upload-multi` → `worker/tasks/full_pipeline_multi.py` (`docs/PLAN-2026-06-29-upload-multi-media.md`) |
| 자막 (Whisper 환각 필터 등) | `backend/app/services/subtitles.py` + `worker/tasks/subtitle.py` |
| 프론트 페이지 수정 | `frontend/src/pages/<페이지>.tsx` (라우팅: `frontend/src/App.tsx`) |
| 업로드 플로우 (단계별 UI) | `frontend/src/pages/upload/Step*.tsx` + `UploadPage.tsx` |
| API 클라이언트/타입 | `frontend/src/api/client.ts`, `types.ts`, `errors.ts` |
| 전역 상태 (auth/theme/ui) | `frontend/src/store/auth.ts`, `theme.ts`, `ui.ts` (Zustand) |
| 어드민 기능 | `backend/app/routes/admin.py` + `frontend/src/pages/AdminPage.tsx` + `backend/tests/test_admin.py` |
| 챌린지 기능 | `backend/app/{routes,models,schemas}/challenge*.py` + `frontend/src/pages/Challenge*.tsx` |
| 게시물 글 수정 | `PATCH /videos/posts/{id}` (`backend/app/routes/videos.py`, `PostUpdateRequest`) + `frontend/src/pages/PostEditPage.tsx` (`/posts/:id/edit`) |
| 팔로우 | `backend/app/models/follow.py` + `app/routes/users.py`(follow/followers/following) + `frontend/src/pages/{UserProfilePage,FollowListPage}.tsx` |
| 친구 초대 (referral) | `backend/app/services/referral.py` + `users.referral_code/referred_by_id` + `GET /users/me/referral` + `frontend/src/pages/InvitePage.tsx` (`/invite`), `?ref=` 캡처는 `App.tsx` |
| 설문 기능 | `backend/app/{models,schemas,routes}/survey.py` + `frontend/src/pages/SurveyPage.tsx` + `AdminSurveys*.tsx` |
| 배포/인프라 | `scripts/deploy.sh` + `Dockerfile` + `CLAUDE.md`(blue-green 주의사항) |
| 워커 배포 | 실제 운영: `stack-health-worker@{1,2}.service`(systemd --user, host 전용) + `scripts/deploy.sh` — 인스턴스 수는 `worker/.env`의 `WORKER_INSTANCES`. `worker/DEPLOY.md`/`worker/stackhealth-worker@.service`/`worker/deploy.sh`는 별도 `/opt` 전용서버 경로(미사용). 상세: `CLAUDE.md`(워커 멀티 인스턴스 주의사항) |
| 에러 코드 | `ERR_CODE.md` + `backend/app/services/error_codes.py` |
| 환경변수 | `.env.example` + `backend/ENV_VARS.md` |

## Backend (`backend/`)

- **진입점**: `app/main.py` — FastAPI app, 라우터 등록, 정적 SPA fallback
- **설정**: `app/config.py` (pydantic settings, `.env` 로드)
- **DB**: `app/database.py` / 마이그레이션 `alembic/`
- **routes/** (도메인별 API): `auth` `videos` `feed` `rewards` `admin` `comments` `history` `challenges` `users` `survey`
- **models/** (SQLAlchemy): `user` `video` `post` `post_like` `post_view` `comment` `reward` `challenge` `admin_log` `lnauth_challenge` `app_links` `survey` `survey_response`
- **schemas/** (Pydantic): `user` `video` `reward` `challenge` `survey`
- **services/** (비즈니스 로직):
  - `auth.py` JWT / `google_oauth.py` Google 로그인 / `lnauth.py` Lightning 로그인(LNURL-auth)
  - `reward.py` 리워드 지급 (Blink Lightning) / `share_token.py` 공유 링크 토큰
  - `r2.py` Cloudflare R2 업로드 / `job_queue.py` Redis 잡 큐 enqueue
  - `subtitles.py` 자막 생성·환각 필터 / `rate_limit.py` / `notify.py` 텔레그램 알림 / `error_codes.py`
- **tests/**: 도메인별 `test_*.py` (pytest) — 실행: `cd backend && .venv/bin/pytest -q`

## Frontend (`frontend/`)

- **진입점**: `src/main.tsx` → `src/App.tsx` (React Router 라우팅 + RequireAuth)
- **SPA 라우트 → 페이지** (`src/pages/`):
  - `/` FeedPage, `/upload` UploadPage(+`upload/Step*.tsx`), `/profile` ProfilePage
  - `/login` LoginPage (`/login/lightning` `/login/email` `/login/register`)
  - `/challenges` ChallengePage (`create` `:id` `:id/edit` `:id/dashboard`, `/my-challenges`)
  - `/survey/:slug` SurveyPage (공개 익명 설문, 비로그인 접근)
  - `/admin/surveys` AdminSurveysListPage / `/admin/surveys/new` & `/:id/edit` AdminSurveyEditorPage / `/:id/responses` AdminSurveyResponsesPage
  - `/admin` AdminPage, `/leaderboard`, `/settings`, `/team`, `/terms`
  - `/shorts/:shareToken` SharedVideoPage (비로그인 공유), `/users/:userId` UserProfilePage
- **components/**: `VideoCard` `CommentSheet` `BottomNav` `SideNav` `UpdateBanner` 등 공용 UI
- **api/**: `client.ts`(fetch wrapper) `types.ts` `errors.ts`
- **store/** (Zustand): `auth` `theme` `ui` / **hooks/**: `useVersionCheck`
- **utils/**: `subtitles` `sweat` `calendar` `profileColor` / **lib/**: `constants` `platform`
- **테스트**: 유닛 `src/__tests__/` (Vitest) / E2E `e2e/*.spec.ts` (Playwright)
- 빌드: `cd frontend && npm run build`

## Worker (`worker/`)

- **진입점**: `worker.py` — Redis 큐 폴링, ffmpeg 동시실행 리스 세마포어(Lua)
- **tasks/**: `full_pipeline.py`(단일 영상 업로드 파이프라인) `full_pipeline_multi.py`(다중 미디어 파이프라인) `compose.py`(영상≤1+이미지≤5 순서대로 concat) `merge.py`(영상+오디오 병합) `image_merge.py` `subtitle_extract.py` `subtitle.py`(+`build_srt_from_text` 텍스트→자막) + `backfill_*.py`(일회성 백필)
- `queue_client.py` Redis 잡 dequeue/ack / `notify.py` 텔레그램 / `health_check.py`
- 배포: 실제 운영은 `stack-health-worker@{1,2}.service`(systemd --user, host 전용 유닛) — 상세 `CLAUDE.md` 참고. repo의 `deploy.sh`/`stackhealth-worker@.service`/`DEPLOY.md`는 별도 `/opt` 전용서버 경로(이 서버에서 미사용)

## 운영/배포

- **Blue-Green**: blue=8017, green=8018, nginx upstream 전환 — **반드시 `CLAUDE.md` 숙지** (실제 nginx 설정은 `/etc/nginx/conf.d/stackhealth-upstream.conf`)
- `scripts/`: `install.sh` `dev.sh` `test.sh` `deploy.sh` `start.sh` + `hooks/`
- `Dockerfile` multi-stage (frontend build → backend serve)
- 버전: `VERSION` (push 전 bump 필수)

## 문서

| 문서 | 내용 |
|---|---|
| `docs/ARCHITECTURE.md` | 시스템 아키텍처 (구성도, 데이터 흐름) |
| `SPEC.md` | 구현 스펙 |
| `docs/vision.md` | 제품 비전, Phase A/B 경계 |
| `docs/team-vision.md` | multi-agent 토론 공통 컨텍스트 |
| `docs/discussion-report-spec.md` | 토론/보고 워크플로 단일 원본 |
| `AGENTS.md` | 최상위 작업 계약 (에이전트 14종, 검증 기준) |
| `ERR_CODE.md` | 에러 코드 정의 |
| `meetings/INDEX.md` | 회의록 인덱스 |

## 탐색하지 않아도 되는 곳

`.omc/` `.omx/` `.playwright-mcp/` `.worktrees/` `.wrangler/` `archive-meta/` `output/` `tmp/` `subtitle-test/` `frontend/playwright-report*/` `frontend/test-results/` 루트의 `*.png` — 세션 산출물/아카이브. 명시 요청 없으면 읽지 않는다.
