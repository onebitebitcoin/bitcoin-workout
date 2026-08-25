# 구현 진행 상황 — 점수 체계 제거

> 되돌림 지점: `stackhealth-v0.19.1` (tag, origin push 완료)

## 확정된 결정
- 땀방울/포인트 메커니즘 전면 제거
- 리더보드: 접근 경로 + API + 페이지 제거 (데이터 원천인 `reward_points`가 사라져 숨김만으로는 동작 불가)
- 하루 업로드 2회 제한: 해제 (댓글 일일 제한은 유지)
- `reward_points` 테이블: drop 마이그레이션 `c7d8e9f0a1b2`

## 완료된 Phase
- [x] Phase 1: 백엔드 — `services/timeframe.py` 분리 + reward 모듈/라우트/모델/스키마 제거, worker 파이프라인 적립 제거
- [x] Phase 2: alembic `c7d8e9f0a1b2_drop_reward_points` — upgrade/downgrade 왕복 검증
- [x] Phase 3: 백엔드 테스트 정리 (330 passed)
- [x] Phase 4: 프론트 — 포인트 뱃지/리더보드/업로드 제한 UI 제거 (76 passed)
- [x] Phase 5: i18n 고아 키 23개 + e2e 스펙 + SPEC.md/INDEX/ARCHITECTURE/AGENTS 정리
- [x] Phase 6: 린트·테스트·빌드 전체 통과

## 남은 작업
- [ ] 커밋 (사용자 승인 대기)
- [ ] 브랜딩 전환 — 마크는 Coin Play 확정, 나머지 항목은 사용자와 논의 필요

## 논의 필요 — 이번 작업 중 생긴 것
- `BottomNav` 리더보드 자리를 알림 탭으로 교체함 (5탭 유지 → FAB 중앙 정렬 보존). 되돌리기 쉬움.
- `AGENTS.md` 20~21행이 아직 "스코어/비트코인 리워드"를 제품 핵심으로 서술 — 브랜딩 라운드에서 함께 정리
