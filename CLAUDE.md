# Stack Health — Claude Code 작업 지침

## 탐색 인덱스 — 파일 탐색 전 필수 (MANDATORY)

> **프로젝트 파일을 탐색(ls/glob/grep/디렉토리 순회)하기 전에 반드시 `docs/INDEX.md`를 먼저 읽는다.**
> 인덱스에 "작업 유형 → 봐야 할 파일" 매핑이 있으므로, 대부분의 작업은 인덱스만 보고 대상 파일로 바로 이동할 수 있다.

- 아키텍처 이해가 필요하면 `docs/ARCHITECTURE.md` 참조 (구성도, 데이터 흐름, 배포 구조).
- 디렉토리/파일 구조를 바꾸면 `docs/INDEX.md`를 같은 커밋에서 갱신한다.
- `.omc/` `.omx/` `archive-meta/` `output/` `tmp/` 등 세션 산출물 디렉토리는 탐색하지 않는다 (인덱스 하단 목록 참조).

## 토큰 절감 규칙

- **조사형 작업은 Explore 서브에이전트(haiku)에 위임**: "어디서 X를 하는지 찾아줘" 류의 광범위 탐색은 메인 컨텍스트에 파일 덤프를 쌓지 말고 Explore에 위임해 결론만 받는다. 단일 파일 확인은 직접 Read(offset/limit)로 필요한 부분만 읽는다.
- 같은 파일을 같은 턴에 다시 읽지 않는다. 수정 후 재확인 Read 금지 (Edit 실패 시 에러가 난다).
- 스크린샷/리포트 등 산출물은 루트가 아닌 `output/` 아래에 생성한다.

## 사용량 로깅 + 코칭 (.claude/usage/)

- UserPromptSubmit/Stop 훅이 질문·응답시간·토큰·재요청 여부를 `.claude/usage/usage-log.jsonl`에 자동 기록한다 (로컬 전용, gitignore).
- `/usage-coach` 실행 시 리포트 + 프롬프트 개선 제안 + 모델 라우팅 가이드를 생성하고 `.claude/usage/coach-hints.md`를 갱신한다.
- 훅 스크립트: `.claude/hooks/usage_prompt.py`, `usage_stop.py`, `usage_report.py`

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

### 워커(worker) 멀티 인스턴스 — 핵심 주의사항

**실제 운영 워커**: `measly` 유저 systemd `--user` 템플릿 유닛 `stack-health-worker@1`, `stack-health-worker@2` (`~/.config/systemd/user/stack-health-worker@.service`, repo에는 없음 — 다른 `stack-health-app-*` 유닛들과 동일하게 호스트 전용 파일). `WorkingDirectory=/home/measly/stack-health/worker`에서 repo 코드를 직접 실행한다.

- 인스턴스 개수는 `worker/.env`의 `WORKER_INSTANCES`로 정하고, `scripts/deploy.sh`가 이 값을 읽어 `stack-health-worker@1..N`을 전부 재시작한다 (push 배포 시 자동).
- `backend/app/services/cartoon.py`, `muscle_heat.py`는 `WORKER_INSTANCES`로 코어 수를 나눠 프로세스 풀 크기를 정하므로, 인스턴스 수를 바꾸면 반드시 `worker/.env`의 `WORKER_INSTANCES`도 같이 맞춰야 한다 (기본 8코어 기준 2인스턴스 권장, `(8-2)/2=3` 프로세스/인스턴스).
- **`worker/deploy.sh` + repo의 `worker/stackhealth-worker@.service`는 이것과 다른, 별도의 `/opt/stackhealth-worker` 단일 전용서버 배포 경로용이다 (`worker/DEPLOY.md` 참고). 이 서버에는 `/opt/stackhealth-worker`가 존재하지 않고, 어떤 자동화도 그 스크립트를 실행하지 않는다 — 혼동 금지.**

### 장애 이력 (2026-05-31)

- **증상**: `https://stackhealth.life` 전체 502/521, 데이터가 보이지 않음
- **원인**: deploy.sh가 `/etc/nginx/conf.d/stackhealth-upstream.conf`를 8018로 바꿨으나 green 슬롯이 실행되지 않았음. DB/백엔드 자체는 정상이었음.
- **해결**: `/etc/nginx/conf.d/stackhealth-upstream.conf`를 8017(blue)로 수정 후 reload
- **재발 방지**: `deploy.sh` Step 7이 실제 nginx 설정 파일을 직접 업데이트하도록 수정 완료
