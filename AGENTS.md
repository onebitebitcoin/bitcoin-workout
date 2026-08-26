# 작업 지침 — 비트코이너는 뭐하고 사나

> **실가동 에이전트**: `.claude/agents/` 14개만 사용한다.
> OMX/OMC 아카이브는 `archive-meta/`에 보존되어 있으며 현재 활성화되지 않는다.
> OMX 자동생성 계약은 `AGENTS-omx.md` 참조.

이 파일은 이 저장소의 Claude Code 및 Codex용 최상위 작업 계약이다. `.claude/agents`, `.claude/commands`, `docs/discussion-report-spec.md`, `docs/team-vision.md`, `docs/vision.md`, `SPEC.md`를 기준으로 반영한다.

## 기본 원칙

- 모든 사용자-facing 답변은 한국어로 작성한다. 코드, 로그, 에러 메시지는 원문을 유지한다.
- 추측보다 근거를 우선한다. 완료 보고 전 반드시 테스트/빌드/파일 확인 등 검증 증거를 수집한다.
- 명확하고 되돌릴 수 있는 작업은 자동으로 진행한다. 파괴적 작업, 비밀키, 프로덕션 외부 상태 변경은 사용자 확인 없이는 하지 않는다.
- 새 의존성은 명시 요청이 없으면 추가하지 않는다.
- 기존 패턴과 유틸을 우선 재사용하고, 불필요한 추상화보다 작고 되돌리기 쉬운 변경을 선호한다.
- 구현/수정 후 가능한 범위에서 backend pytest, frontend build/lint/e2e 등 관련 검증을 실행한다.

## 프로젝트 요약

- 제품: 비트코인·일상 두 카테고리로 비트코이너의 하루를 60초 기록으로 공유하는 Bitcoiners 플랫폼
- 핵심 명제: 여러 카테고리의 기록을 하나의 정체성(비트코이너)으로 묶어내는 것이 핵심이며, 진짜 동기는 커뮤니티와 성장 피드백이다.
- Phase A 목표: MVP 런칭, 영상 업로드 + 피드 + 챌린지 + 어드민 운영 도구
- 주요 문서:
  - `docs/INDEX.md` — **파일 탐색 전 필수로 읽는 탐색 인덱스** (작업 유형 → 파일 매핑)
  - `docs/ARCHITECTURE.md` — 시스템 아키텍처 (구성도, 데이터 흐름, 배포)
  - `SPEC.md` — 구현 스펙
  - `docs/vision.md` — 제품 비전과 Phase A/B 경계
  - `docs/team-vision.md` — multi-agent 토론 공통 프로젝트 컨텍스트
  - `docs/discussion-report-spec.md` — 토론/보고 워크플로 단일 원본
  - `meetings/INDEX.md` — 회의록 인덱스

## 기술 스택과 실행 명령

| 영역 | 스택/도구 | 주요 명령 |
|---|---|---|
| Frontend | React + Vite + TailwindCSS + TanStack Query + Zustand | `cd frontend && npm run build` |
| Backend | Python + FastAPI + SQLAlchemy + Alembic | `cd backend && .venv/bin/pytest -q` |
| DB | SQLite(dev) / PostgreSQL(prod) | Alembic migrations under `backend/alembic/` |
| 배포 | Docker + 자체 서버 | `Dockerfile` |

## 코드베이스 구조

- `frontend/src/App.tsx` — SPA 라우팅. `/admin`은 `AdminPage`로 연결된다.
- `frontend/src/pages/` — 주요 페이지.
- `frontend/src/api/` — API client/types.
- `backend/app/main.py` — FastAPI app, 라우터 등록, 정적 SPA fallback.
- `backend/app/routes/` — auth/feed/videos/comments/challenges/admin API.
- `backend/app/models/` — SQLAlchemy 모델.
- `backend/tests/` — pytest API 테스트.

## 최신 문서 규칙

라이브러리, 프레임워크, SDK, API 사용법이 관련되면 현재 문서 확인이 필요하다.

1. Codex 환경에서는 `context7` MCP/도구가 가능하면 먼저 사용한다.
2. 부족하면 공식 문서/공식 저장소만 근거로 확인한다.
3. 확인이 불가능하면 버전 불확실성을 명시한다.

## 개발 워크플로

1. 요청 범위를 파악하고 관련 문서를 먼저 읽는다.
2. 단순 조회는 `omx explore` 또는 `rg`/파일 읽기로 근거를 확보한다.
3. 복잡한 변경은 계획 → 구현 → 검증 → 보고 순서로 진행한다.
4. 동작 변경/리팩터링은 가능한 한 기존 테스트로 고정하고, 부족하면 최소 회귀 테스트를 추가한다.
5. 완료 보고에는 변경 파일, 검증 명령, 남은 리스크를 포함한다.

## 검증 기준

- Backend 변경: `cd backend && .venv/bin/pytest -q`
- Frontend 변경: `cd frontend && npm run build`; 가능하면 관련 Playwright/e2e 실행
- 어드민/API 변경: `backend/tests/test_admin.py` 포함 확인
- UI 변경: 스크린샷 또는 브라우저 확인이 가능하면 수행

## 보안/운영 주의

- `.env`, API key, JWT secret, admin secret을 출력하거나 커밋하지 않는다.
- `ADMIN_SECRET_KEY` 기반 어드민 API는 단순 헤더 인증이므로 삭제/ban 기능 변경 시 감사 로그와 테스트를 우선 확인한다.
- 업로드/댓글은 어뷰징·콘텐츠 모더레이션 리스크가 높다.
- 사용자 입력은 API 경계에서 Pydantic/서버 검증을 우선한다.

## 팀 아키텍처

실가동 Claude Code 에이전트 (`.claude/agents/` 14개):

| 역할 | 담당 | 사용 시점 |
|---|---|---|
| `architect` | 전체 시스템 설계, 컴포넌트 인터페이스, 기술 결정 | 구조 변경, 신규 기능 설계 |
| `frontend` | React + Vite + TailwindCSS + Zustand + TanStack Query 구현 | UI/UX 작업 |
| `backend` | FastAPI + SQLAlchemy + Pydantic 구현 | API/서비스 레이어 |
| `dba` | SQLAlchemy 모델, Alembic 마이그레이션, 쿼리 최적화 | DB 스키마 변경 |
| `devops` | Docker 빌드, 서버 배포, 환경변수 관리 | 배포/인프라 |
| `designer` | UX 흐름, 컴포넌트 스펙, 디자인 시스템 | `/discuss` 토론 |
| `developer` | 기술 타당성, 구현 난이도, 스택 적합성 | `/discuss` 토론 |
| `planner` | 사업 우선순위, 로드맵 정합성, 범위 관리 | `/discuss` 토론 |
| `devil` | 비판적 반론, 간과된 리스크·맹점 드러내기 | `/discuss` 토론 |
| `qa` | 검증 지표, 실패 시나리오, 테스트 코드 | `/discuss` + 검증 |
| `finance` | 비용 구조, 손익분기 분석 | `/discuss` 토론 |
| `marketing` | 채널 전략, 고객 획득, 경쟁사 분석 | `/discuss` 토론 |
| `researcher` | 시장조사, 외부 데이터 수집 | `/discuss` 토론 |
| `ops` | 운영 프로세스 최적화, SOP 설계 | `/discuss` 토론 |

### 토론 사용 규칙

- 토론/보고/인터뷰는 `docs/discussion-report-spec.md`를 단일 원본으로 따른다.
- 새 안건 토론: `/discuss` 명령어 → 9개 토론 역할 2-round
- 모든 회의록: `meetings/YYYY-MM-DD-HHMM-<slug>.md` + `meetings/INDEX.md` 추가

## 아카이브된 OMX/OMC 스킬

과거 OMX project-scope 스킬은 `archive-meta/codex/`에, OMC 에이전트 카탈로그는 `archive-meta/omc/`에 보존됨.
현재 가동 중 아님. 복원 방법: `mv archive-meta/codex .codex && mv archive-meta/omc .omc`

## 배포 인프라 — 반드시 숙지

### Blue-Green 배포 구조

| 슬롯 | 포트 | 상태 |
|------|------|------|
| blue | 8017 | 현재 활성 슬롯 (`.deploy-slot` 기준) |
| green | 8018 | 다음 배포 시 기동, 전환 후 종료 |

- 평상시에는 **한 슬롯만** 실행된다. 두 슬롯이 동시에 상시 실행되지 않는다.
- 배포 시에만 잠깐 두 슬롯이 겹치고, nginx 전환 후 이전 슬롯이 종료된다.
- 두 슬롯 모두 **동일한 PostgreSQL DB**를 바라본다.

### Nginx Upstream — 핵심 주의사항

**실제 nginx가 읽는 파일**: `/etc/nginx/conf.d/stackhealth-upstream.conf`

**repo 파일**: `nginx/upstream.conf` → nginx가 직접 읽지 않음. 참조용.

> **절대 하지 말 것**: `nginx/upstream.conf`만 수정하고 `nginx reload`해도 upstream이 바뀌지 않는다.
> upstream 변경이 필요하면 반드시 `/etc/nginx/conf.d/stackhealth-upstream.conf`를 수정해야 한다.

upstream 수동 변경 방법:
```bash
sudo bash -c 'cat > /etc/nginx/conf.d/stackhealth-upstream.conf << EOF
upstream stackhealth_app {
    server 127.0.0.1:8017;   # blue=8017, green=8018
    keepalive 32;
}
EOF'
sudo nginx -s reload
```

`deploy.sh`는 두 파일을 모두 업데이트하도록 수정되어 있다 (`scripts/deploy.sh` Step 7).

### 장애 이력 (2026-05-31)

- **증상**: `https://stackhealth.life` 전체 502/521, 데이터가 보이지 않음
- **원인**: deploy.sh가 `/etc/nginx/conf.d/stackhealth-upstream.conf`를 8018로 바꿨으나 green 슬롯이 실행되지 않았음. DB/백엔드 자체는 정상이었음.
- **해결**: `/etc/nginx/conf.d/stackhealth-upstream.conf`를 8017(blue)로 수정 후 reload
- **재발 방지**: `deploy.sh` Step 7이 실제 nginx 설정 파일을 직접 업데이트하도록 수정 완료

## Git / 커밋

- 기존 `.git`은 절대 삭제하지 않는다. 최초 프로젝트 생성 요청이 아닌 이상 `rm -rf .git` 금지.
- 커밋이 필요하면 변경 의도와 검증 내용을 명확히 남긴다.
- 현재 세션의 상위 지침에 Lore commit protocol이 있으면 그 형식을 우선한다.

<!-- OMX 자동생성 블록은 AGENTS-omx.md로 이전됨 -->
