# 구현 진행 상황 — Bitcoiners 리브랜딩

> 되돌림 지점: `stackhealth-v0.19.1` (tag, origin push 완료)
> 선행 커밋: `851b043` 땀방울 점수 체계 제거

## 확정 브랜드

| 항목 | 값 |
|------|-----|
| 앱 이름 | Bitcoiners / 비트코이너스 |
| 도메인 | bitcoiners.life (stackhealth.life는 301 예정) |
| 태그라인 | 비트코이너는 뭐하고 사나 |
| 마크 | Coin Play — 오렌지 원 + 재생 삼각형 + 비트코인 틱 |
| 액센트 | #F7931A (테마 `bitcoin`, 기본값) |
| 카테고리 | 비트코인 · 일상 (2종) |

## 완료 — 코드

- [x] 마크 교체 + 웹/모바일 아이콘 자산 + PWA 매니페스트
- [x] 프론트 문자열 — index.html, i18n ko/en 10네임스페이스, llms/robots/sitemap
- [x] 백엔드 — FastAPI title, 공유 카드 OG 생성부, worker 스크립트 문구
- [x] `bitcoin` 테마 추가 + 기본값 (기존 6종 보존)
- [x] 카테고리 2종 전환 + 마이그레이션 `004aa221ea8d`
- [x] "기록 시간대" 입력 제거 — 영상 저장 시간 기준. DB 컬럼은 보존
- [x] 모바일 앱 표시명·도메인 (패키지 ID 보존)
- [x] 이용약관 재작성 — 존재하지 않는 기능 조항 제거
- [x] i18n ko/en 정합성 회귀 테스트 추가

## 완료 — 문서

- [x] SPEC.md, CLAUDE.md, AGENTS.md, docs/INDEX.md, ARCHITECTURE.md, vision.md, team-vision.md
- [x] `docs/DOMAIN-CUTOVER.md` 신규 — 도메인 전환 절차, 배포 위험, dev 환경

## 남은 결정 — 사용자

### 1. 배포 전략 (커밋보다 우선)

`reward_points` DROP이 blue-green 창에 걸린다. 구 슬롯이 없어진 테이블을
조회하는 30~60초 동안 업로드·댓글·모더레이션이 실패한다. 업로드는 최대 3분
처리를 끝내고 마지막 저장에서 깨져 체감 손실이 가장 크다.

| 안 | 창 영향 | 남는 비용 |
|----|---------|-----------|
| A 감수 | 있음 | 없음 |
| B DROP 연기 | 없음 | 유저 삭제 FK 위반 (관리자 전용, 후속 배포까지) |

상세는 `docs/DOMAIN-CUTOVER.md` 1-4.

### 2. `frontend/src/pages/upload/StepCaption.tsx`

죽은 코드. 어디서도 import되지 않는다. 삭제 여부 미정.

### 3. 서버 작업 (사용자 직접)

DNS · certbot · nginx server_name + 301 · Google OAuth redirect URI 재등록.
절차는 `docs/DOMAIN-CUTOVER.md`.

## 별도 — 이번 범위 밖

- **파일 중복 차단 미작동**: `videos.py:174,854`가 해시 자리에 R2 키를 넣고
  조회 쿼리가 없다. 같은 영상을 반복 업로드할 수 있다. 리브랜딩 이전부터.
- **e2e가 CI에서 안 돈다**: `RUN_E2E=1` 게이팅 때문에 `og:image` 단언이
  오래 깨진 채 방치됐다. 실행은 1분 남짓.
