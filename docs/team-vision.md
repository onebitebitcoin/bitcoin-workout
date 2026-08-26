# 팀 비전 — Bitcoiners

## 프로젝트 개요

- **프로젝트명**: Bitcoiners (비트코이너스)
- **한 줄 설명**: 비트코이너의 하루를 60초 영상으로 공유하는 커뮤니티
- **태그라인**: 비트코이너는 뭐하고 사나
- **핵심 목표**: 3개월 내 사용자 100명 확보
- **현재 단계**: MVP 운영 직전 (v0.26.x)
- **대표자**: 한입 비트코인
- **런칭 목표일**: 2026-05-28
- **기술 스택**: React + FastAPI (웹), Railway 배포, Cloudflare R2 CDN, Redis + ffmpeg 오디오 병합

## 영상 인프라 아키텍처

### 구현된 아키텍처: Cloudflare R2 + 외부 워커

| 컴포넌트 | 역할 | 상태 |
|----------|------|------|
| **Cloudflare R2** | 영상 원본 저장 (presigned URL 직접 업로드) | ✅ 구현됨 |
| **Railway FastAPI** | 백엔드 API + React SPA 서빙 | ✅ 구현됨 |
| **Ubuntu 워커** | ffmpeg 오디오+영상 병합 | ✅ 구현됨 |
| **Redis** | 병합 잡 큐 (워커 미사용 시 in-process fallback) | ✅ 구현됨 |

### 업로드 흐름 (presigned)
```
사용자 → FastAPI (presigned URL 발급) → Cloudflare R2 직접 업로드
       → 업로드 완료 후 FastAPI /videos/confirm → DB 메타데이터 저장
```

### 오디오 병합 흐름
```
사용자 → FastAPI /videos/merge-audio → Redis 큐 enqueue
       → Ubuntu 워커 BRPOP → ffmpeg 병합 → R2 업로드 → 완료
       (Redis 불가 시 FastAPI 프로세스에서 직접 ffmpeg 실행)
```

## 경쟁사 / 레퍼런스

| 서비스 | 참고 포인트 |
|--------|------------|
| **Instagram Reels / YouTube Shorts** | 영상 피드 UX 레퍼런스 |
| **Strava** | 운동 기록 커뮤니티 — 일상 카테고리에 담기는 운동 기록 콘텐츠의 비교 대상 |

## 핵심 재무 지표

- **수익 모델**: 광고 기반
- **월 목표 매출**: 100만원
- **손익분기**: 초기 단계 — 추후 업데이트

## 핵심 지표 (KPI)

| 지표 | 목표 |
|------|------|
| 가입 사용자 | 100명 (3개월) |
| 영상 업로드 수 | 측정 예정 |
| 주간 활성 사용자 | 측정 예정 |
| 광고 수익 | 월 100만원 |

## 현재 Phase

- **Phase A**: MVP 런칭 — 핵심 기능(영상 업로드 + 피드 + 챌린지 + 댓글) 구현 완료, 런칭 대기 (2026-05-28)
- **Phase B**: 어드바이저 시스템, 업로드 전 5가지 질문, 월 이벤트/루틴, 광고 SDK
