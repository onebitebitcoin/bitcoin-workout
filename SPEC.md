# SPEC.md — 나의 운동을 기록하자

> 버전: 0.52.0 (운영 중)
> 런칭 목표: 2026-05-28
> 최종 업데이트: 2026-05-31
>
> **이 문서는 코드 기준으로 작성됩니다. 코드가 진실 원본이며, 이 문서는 코드를 설명합니다.**

---

## 1. 프로젝트 개요

운동 쇼츠를 SNS 피드(인스타 릴스/유튜브 쇼츠 형태)로 공유하고, 매일 나의 운동을 기록하며 꾸준한 운동 습관을 만들어가는 웹 플랫폼.

### 핵심 가치
- 운동 습관 형성 + 운동 기록 공유
- 커뮤니티와 함께하는 동기 부여

### MVP 목표
- 사용자: 3개월 내 100명 확보
- 수익: 광고 기반, 월 100만원 목표 (MAU 1,400명+ 필요 — 장기 목표)
- 초기 운영비: 10만원 (기확보)

---

## 2. 타임존 정책

> **이 규칙을 어기면 히스토리 캘린더와 스트릭이 날짜 경계에서 어긋납니다.**

### 원칙

| 레이어 | 규칙 |
|--------|------|
| **DB** | 모든 datetime 컬럼은 `TIMESTAMPTZ` (UTC). naive datetime 저장 금지 |
| **Backend Python** | `datetime.now(timezone.utc)` 사용. `datetime.now()` (naive) 사용 금지 |
| **Backend API 응답** | 모든 datetime 필드는 ISO 8601 UTC 오프셋 포함 (`2026-05-28T15:30:00+00:00`) |
| **Frontend** | `new Date(isoString)` — 브라우저가 UTC 파싱 → 클라이언트 timezone 자동 표시 |
| **Timezone-aware API** | 사용자에게 날짜/시간을 보여주거나 히스토리 캘린더를 그릴 때만 `?timezone=` 쿼리 파라미터 또는 `X-Client-Timezone` 헤더로 클라이언트 timezone을 명시적으로 수신 |

### 금지 사항

- `DateTime` (timezone=False) SQLAlchemy 컬럼 신규 추가 금지
- `KST = timezone(timedelta(hours=9))` 하드코딩 및 DB 비교에 사용 금지
- `datetime.now()` 또는 `datetime.utcnow()` (naive) 사용 금지 → `datetime.now(timezone.utc)` 사용
- `.replace(tzinfo=None)` 으로 timezone 정보를 제거한 뒤 DB에 저장 금지
- `_DB_TZ = ZoneInfo("Asia/Seoul")` 류의 "DB가 KST 저장" 가정 금지

### 글로벌 UTC 비즈니스 기준

서비스의 집계 기준은 국가별 로컬 자정이 아니라 **글로벌 UTC 캘린더**입니다.
사용자에게 보여주는 날짜/시간만 브라우저 또는 `X-Client-Timezone` 기준 로컬 타임으로 변환합니다.

| 항목 | 설명 |
|------|------|
| 주간 경계 | UTC 기준 월요일 00:00 시작 |
| 월간 통계 | UTC 기준 매월 1일 00:00 시작 |
| 조회수 일일 중복 제거 | UTC 자정 기준 리셋 |
| 화면 표시 | API의 UTC ISO datetime을 사용자 로컬 타임존으로 변환해 표시 |

`X-Client-Timezone`은 표시/캘린더용 보조 정보이며, 집계 기간을 바꾸면 안 됩니다.

---

## 4. 기술 스택

| 영역 | 기술 |
|------|------|
| Frontend | React 18 + Vite + TailwindCSS + shadcn/ui |
| Backend | Python 3.11 + FastAPI + SQLAlchemy 2.0 + Alembic |
| DB (개발) | SQLite |
| DB (프로덕션) | PostgreSQL |
| 영상 저장 | Cloudflare R2 (presigned URL 직접 업로드) |
| 영상 서빙 | Cloudflare CDN (R2 퍼블릭 도메인) |
| 배포 | Docker + 자체 서버 (FastAPI가 React 빌드 파일도 서빙) |
| 인증 | JWT (python-jose) + Google OAuth (옵션) + LNAuth (옵션) |
| 아이콘 | lucide-react |
| HTTP 클라이언트 | TanStack Query (React Query v5) |
| 상태 관리 | Zustand |
| 오디오 병합 | ffmpeg (Ubuntu 외부 워커) + Redis 큐 |
| 워커 큐 | Redis (merge-audio 잡 분배) |

### 환경 변수 (.env)
```
# Database
DATABASE_URL=sqlite:///./dev.db

# JWT
SECRET_KEY=<random 32 bytes>
ACCESS_TOKEN_EXPIRE_MINUTES=10080

# Cloudflare R2
R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET_NAME=
R2_PUBLIC_URL=https://<bucket>.r2.dev

# Admin
ADMIN_SECRET_KEY=<random string>

# App
ENVIRONMENT=development
PORT=8000
APP_BASE_URL=http://localhost:8000

# Google OAuth (선택 — 미설정 시 Google 로그인 비활성화)
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# Redis (선택 — 미설정 시 백엔드 직접 ffmpeg fallback)
REDIS_URL=redis://localhost:6379/0
```

---

## 5. 프로젝트 구조

```
stack_health/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── models/
│   │   │   ├── user.py
│   │   │   ├── video.py
│   │   │   ├── post.py
│   │   │   ├── comment.py
│   │   │   ├── challenge.py
│   │   │   ├── lnauth_challenge.py
│   │   │   └── admin_log.py
│   │   ├── schemas/
│   │   ├── routes/
│   │   │   ├── auth.py
│   │   │   ├── videos.py
│   │   │   ├── feed.py
│   │   │   ├── comments.py
│   │   │   ├── challenges.py
│   │   │   ├── history.py
│   │   │   ├── users.py
│   │   │   └── admin.py
│   │   ├── services/
│   │   │   ├── auth.py
│   │   │   ├── r2.py
│   │   │   ├── google_oauth.py
│   │   │   ├── lnauth.py
│   │   │   └── job_queue.py
│   │   └── middleware/
│   ├── alembic/
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── pages/
│       ├── components/
│       ├── api/
│       └── store/
├── worker/
│   ├── worker.py
│   ├── tasks/merge.py
│   ├── queue_client.py
│   └── DEPLOY.md
├── scripts/
├── SPEC.md
└── VERSION
```

---

## 6. 데이터베이스 스키마

### users
```sql
id              INTEGER PRIMARY KEY
email           TEXT UNIQUE                -- nullable (LNAuth/OAuth 사용자는 이메일 없을 수 있음)
username        TEXT UNIQUE NOT NULL
password_hash   TEXT                       -- nullable (OAuth 전용 계정은 패스워드 없음)
oauth_provider  TEXT                       -- 'google' | null
oauth_sub       TEXT                       -- Google sub 또는 null
lightning_address TEXT                     -- 예: user@walletofsatoshi.com
avatar_url      TEXT
is_admin        BOOLEAN DEFAULT FALSE
created_at      TIMESTAMPTZ DEFAULT now()   -- UTC
```

### videos
```sql
id              INTEGER PRIMARY KEY
user_id         INTEGER REFERENCES users(id)
r2_key          TEXT NOT NULL
cdn_url         TEXT NOT NULL
file_hash       TEXT NOT NULL              -- SHA256, 중복 업로드 차단
duration_sec    INTEGER
status          TEXT DEFAULT 'active'      -- active | rejected | deleted
created_at      TIMESTAMPTZ DEFAULT now()   -- UTC
```

### posts
```sql
id              INTEGER PRIMARY KEY
video_id        INTEGER REFERENCES videos(id) UNIQUE
user_id         INTEGER REFERENCES users(id)
caption         TEXT                       -- 140자 이내
tags            TEXT                       -- JSON 배열: ["홈트", "러닝"]
like_count      INTEGER DEFAULT 0
view_count      INTEGER DEFAULT 0
created_at      TIMESTAMPTZ DEFAULT now()   -- UTC
```

### comments
```sql
id              INTEGER PRIMARY KEY
post_id         INTEGER REFERENCES posts(id)
user_id         INTEGER REFERENCES users(id)
content         TEXT NOT NULL              -- 최대 500자
created_at      TIMESTAMPTZ DEFAULT now()   -- UTC
```

### challenges
```sql
id              INTEGER PRIMARY KEY
title           TEXT NOT NULL              -- 최대 100자
description     TEXT NOT NULL
reward_title    TEXT NOT NULL              -- 달성 보상 타이틀 (최대 80자)
condition_value INTEGER NOT NULL           -- 완료에 필요한 업로드 수
start_date      DATETIME NOT NULL
end_date        DATETIME NOT NULL
categories      JSON DEFAULT []            -- 운동 카테고리 목록
is_active       BOOLEAN DEFAULT TRUE
creator_id      INTEGER REFERENCES users(id) -- null이면 시스템 챌린지
created_at      TIMESTAMPTZ DEFAULT now()   -- UTC
```

### challenge_participations
```sql
id              INTEGER PRIMARY KEY
user_id         INTEGER REFERENCES users(id)
challenge_id    INTEGER REFERENCES challenges(id)
upload_count    INTEGER DEFAULT 0
completed_at    DATETIME                   -- null이면 미완료
joined_at       TIMESTAMPTZ DEFAULT now()   -- UTC
```

### lnauth_challenges
```sql
k1              TEXT PRIMARY KEY           -- 64자 hex challenge
pubkey          TEXT                       -- 서명한 공개키 (verify 후 저장)
verified        BOOLEAN DEFAULT FALSE
created_at      TIMESTAMPTZ DEFAULT now()   -- UTC
```

### admin_logs
```sql
id              INTEGER PRIMARY KEY
action          TEXT NOT NULL              -- 'ban_user' | 'reject_video' | 'delete_video' 등
target_type     TEXT NOT NULL              -- 'user' | 'video' | 'post'
target_id       INTEGER NOT NULL
detail          TEXT
created_at      TIMESTAMPTZ DEFAULT now()   -- UTC
```

---

## 7. API 명세

### 공통
- Base URL: `/api/v1`
- 인증: `Authorization: Bearer <jwt>` (🔒 표시)
- 관리자: JWT `is_admin=true` 필요 (🛡️ 표시)
- 응답 형식: `{ data, error }`
- Trailing slash 없음

### CORS
```python
allow_origins=["*"]
allow_credentials=False
allow_methods=["*"]
allow_headers=["*"]
```

---

### Auth

#### POST `/api/v1/auth/register`
```json
Request:  { "email": str, "username": str, "password": str }
Response: { "data": { "access_token": str, "user": UserSchema } }
```

#### POST `/api/v1/auth/login`
```json
Request:  { "email": str, "password": str }
Response: { "data": { "access_token": str, "user": UserSchema } }
```

#### GET `/api/v1/auth/me` 🔒
```json
Response: { "data": UserSchema }
```

#### PATCH `/api/v1/auth/me` 🔒
```json
Request:  { "username"?: str, "lightning_address"?: str }
Response: { "data": UserSchema }
```

#### GET `/api/v1/auth/check-username`
```
Query: username: str
Response: { "data": { "available": bool } }
```

#### GET `/api/v1/auth/google`
Google OAuth 인증 시작. `GOOGLE_CLIENT_ID` 미설정 시 503.
```
Response: 302 Redirect → Google 인증 URL
```

#### GET `/api/v1/auth/google/callback`
```
Query: code: str
Response: 302 Redirect → <APP_BASE_URL>/?google_token=<jwt> (성공)
          302 Redirect → <APP_BASE_URL>/?error=google_auth_failed (실패)
```

#### GET `/api/v1/auth/lnauth/challenge`
LNAuth 로그인용 challenge 생성.
```json
Response: { "data": { "lnurl": str, "k1": str } }
```

#### GET `/api/v1/auth/lnauth`
LNAuth wallet callback (wallet이 직접 호출).
```
Query: k1: str, sig: str, key: str, tag: str
Response: { "status": "OK" } or { "status": "ERROR", "reason": str }
```

#### GET `/api/v1/auth/lnauth/verify`
프론트엔드가 폴링으로 인증 완료 여부 확인.
```
Query: k1: str
Response: { "data": { "verified": bool, "access_token"?: str, "user"?: UserSchema } }
```

---

### Videos

#### POST `/api/v1/videos/presigned-url` 🔒
R2 업로드용 presigned URL 발급.
```json
Request:  { "filename": str, "content_type": str, "file_size": int, "file_hash": str }
Response: { "data": { "upload_url": str, "r2_key": str } }
```
검증:
- `content_type`: `video/mp4`, `video/quicktime`, `video/webm`
- `file_size`: 최대 50MB (`services/r2.py:MAX_FILE_SIZE`)
- `file_hash`: SHA256 중복 검사 → 중복이면 `409 Conflict`
- 일일 업로드 횟수: 사용자당 3회 초과 시 `429 Too Many Requests`

#### POST `/api/v1/videos/upload` 🔒
서버 사이드 업로드 (브라우저 → 서버 → R2). CORS 제약이 있는 환경에서 사용.
```
Request: multipart/form-data { file: UploadFile }
Response: { "data": { "r2_key": str, "cdn_url": str } }
```

#### POST `/api/v1/videos/confirm` 🔒
R2 업로드 완료 후 DB 저장.
```json
Request:  { "r2_key": str, "duration_sec": int, "caption"?: str, "tags"?: [str], "challenge_id"?: int }
Response: { "data": { "post": PostSchema } }
```
검증:
- `duration_sec`: 5초 이상, 30초 이하
- `tags`: `["홈트", "러닝", "요가", "웨이트", "기타"]` 중 선택 (복수 가능)

#### POST `/api/v1/videos/merge-audio` 🔒
영상과 오디오 파일을 ffmpeg로 병합하는 잡을 큐에 등록.
```
Request: multipart/form-data
  { video_r2_key: str, audio: UploadFile, audio_duration_sec: int,
    post_id: int, caption?: str, tags?: str (JSON) }
Response: { "data": { "job_id": str, "status": "pending" } }
```
- Redis 가용 시: 워커 큐에 잡 등록
- Redis 불가 시: 백엔드에서 직접 ffmpeg 처리 (fallback)
- **주의**: fallback은 in-memory로 상태 관리 → 재배포 시 잡 상태 소실 가능

#### GET `/api/v1/videos/merge-job/{job_id}` 🔒
병합 잡 상태 조회.
```json
Response: { "data": { "job_id": str, "status": "pending|processing|completed|failed",
                       "cdn_url"?: str } }
```

---

### Feed

#### GET `/api/v1/feed`
```
Query: cursor?: int, limit?: int (default 10, max 20)
Response: { "data": { "posts": [PostSchema], "next_cursor": int | null } }
```
- 최신순 정렬
- 비로그인 접근 가능

#### POST `/api/v1/feed/{post_id}/like` 🔒
```json
Response: { "data": { "liked": bool, "like_count": int } }
```
- 토글 방식

#### POST `/api/v1/feed/{post_id}/view` 🔒
```json
Response: { "data": { "view_count": int } }
```
- 조회수 카운트 (하루 동일 영상 중복 view 제외)

---

### Comments

#### GET `/api/v1/comments/{post_id}/comments`
```json
Response: { "data": { "comments": [CommentSchema] } }
```

#### POST `/api/v1/comments/{post_id}/comments` 🔒
```json
Request:  { "content": str }  -- 최대 500자
Response: { "data": { "comment": CommentSchema } }
```

#### DELETE `/api/v1/comments/{post_id}/comments/{comment_id}` 🔒
작성자 본인 또는 관리자만 삭제 가능.
```json
Response: { "data": { "deleted": true } }
```

---

### Challenges

#### GET `/api/v1/challenges`
진행 중인 챌린지 목록.
```
Query: cursor?: int
Response: { "data": { "challenges": [ChallengeSchema], "next_cursor"?: int } }
```

#### POST `/api/v1/challenges` 🔒
새 챌린지 생성.
```json
Request:  { "title": str, "description": str, "reward_title": str,
            "condition_value": int, "start_date": str, "end_date": str,
            "categories"?: [str] }
Response: { "data": { "challenge": ChallengeSchema } }
```

#### GET `/api/v1/challenges/created` 🔒
내가 만든 챌린지 목록.

#### GET `/api/v1/challenges/my` 🔒
내가 참여 중인 챌린지 목록.

#### GET `/api/v1/challenges/titles` 🔒
내가 획득한 챌린지 타이틀 목록.

#### POST `/api/v1/challenges/{challenge_id}/join` 🔒
챌린지 참여.

#### GET `/api/v1/challenges/{challenge_id}/participants`
챌린지 참여자 목록.

---

### History & Users

#### GET `/api/v1/history` 🔒
운동 히스토리 캘린더 데이터.

#### GET `/api/v1/history/me/stats` 🔒
내 스탯 (streak, 총 업로드 수 등).

#### GET `/api/v1/history/{user_id}/profile`
특정 사용자 공개 프로필.

---

### Admin (관리자 전용)

관리자 인증: JWT 토큰 + `is_admin=true` 필요 🛡️

#### GET `/api/v1/admin/videos` 🛡️
콘텐츠 모더레이션용 영상 목록.

#### PATCH `/api/v1/admin/videos/{video_id}/reject` 🛡️

#### GET `/api/v1/admin/users` 🛡️
전체 사용자 목록.

#### POST `/api/v1/admin/users/{user_id}/ban` 🛡️
사용자 비활성화. AdminLog 기록됨.

---

### System

#### GET `/health`
```json
Response: { "status": "ok", "version": "0.26.1" }
```

---

## 8. 영상 업로드 규칙

| 항목 | 제한 |
|------|------|
| 최대 길이 | **30초** |
| 최소 길이 | **5초** |
| 최대 파일 크기 | **50MB** |
| 허용 포맷 | mp4, mov, webm |
| 일일 업로드 | **3회** |
| 중복 차단 | 파일 SHA256 해시 기준 |
| 태그 | 홈트, 러닝, 요가, 웨이트, 기타 |

---

## 10. 화면 목록 (Frontend Routes)

| 경로 | 화면 | 인증 |
|------|------|------|
| `/` | 피드 (풀스크린 세로형 영상) | 불필요 (좋아요·업로드는 요구) |
| `/login` | 로그인 / 회원가입 | — |
| `/upload` | 영상 업로드 (다단계 wizard) | 필요 |
| `/profile` | 내 프로필 + 설정 | 필요 |
| `/history` | 운동 히스토리 캘린더 | 필요 |
| `/challenges` | 챌린지 목록 + 참여 | 필요 |
| `/my-challenges` | 내 챌린지 현황 | 필요 |
| `/challenges/create` | 챌린지 생성 | 필요 |
| `/users/:userId` | 다른 사용자 프로필 | 불필요 |
| `/admin` | 운영자 대시보드 | is_admin |

---

## 11. 배포 설정

### Backend (Docker)
```dockerfile
# Dockerfile 기반 빌드
# CMD: alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT
# healthcheck: /health
```

### Worker (별도 Ubuntu 서버)
- 상세 내용: `worker/DEPLOY.md` 참조
- 필수 환경변수: `REDIS_URL`, `R2_*` (백엔드와 동일)
- 서비스: systemd `stackhealth-worker.service`

---

## 12. 현재 구현 범위

### Phase A (런칭 포함 — v0.26.x)
- 회원가입/로그인 (이메일+비밀번호)
- Google OAuth 로그인 (옵션)
- LNAuth 로그인 (옵션)
- 영상 업로드 (R2 presigned URL 또는 서버 사이드)
- 오디오+영상 merge-audio (Redis 워커 또는 fallback)
- 세로 영상 피드 (최신순)
- 좋아요, 조회수
- 댓글
- 챌린지 시스템 (생성, 참여, 타이틀)
- 운동 히스토리 캘린더 + streak
- 운영자 대시보드 (영상/사용자 관리, AdminLog)

### v2 (미구현)
- 추천 알고리즘
- 광고 SDK
- 푸시 알림
- 팔로우/DM
- AI 운동 인증 검증
- Cloudflare Stream 트랜스코딩
- 업로드 전 5가지 질문 (Phase B 기획)
- 어드바이저 역할 시스템 (Phase B 기획)
- 월 이벤트/루틴 (Phase B 기획)

---

## 13. 운영 SOP

### 콘텐츠 모더레이션
- `/admin/videos` 에서 최신 영상 확인
- 부적절 영상 → `/admin/videos/{id}/reject` (AdminLog 기록됨)
- SLA: 신고 후 24시간 이내 검토

### 사용자 관리
- `/admin/users` 에서 사용자 목록 확인
- 어뷰저 → `/admin/users/{id}/ban` (AdminLog 기록됨)
