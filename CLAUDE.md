# Orange Story — Claude Code 작업 지침

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

### 인프라 식별자는 브랜드명과 무관하다 (MANDATORY)

> **`stackhealth` / `stack-health` / `stack_health`가 이름에 남아 있는 것은 리브랜딩 누락이 아니다. 의도적으로 유지하는 것이니 일괄 치환하지 마라.**

제품명은 Orange Story지만, 아래 식별자들은 서버·스토어·CI에 묶여 있어 이름을 바꾸면 배포나 서비스가 깨진다. 브랜드로 노출되는 곳(화면·메타태그·앱 표시명·공유 카드)은 이미 전부 Orange Story로 정리돼 있다.

| 식별자 | 어디에 묶여 있나 | 바꾸면 |
|---|---|---|
| `/home/measly/stack-health/` | `.github/workflows/deploy.yml`이 이 절대경로로 `scripts/deploy.sh`를 호출 | 배포가 "파일 없음"으로 실패 |
| `stack-health-app-{blue,green,dev}` | 호스트 systemd `--user` 유닛 (repo에 없음) | `deploy.sh`의 슬롯 전환 실패 |
| `stack-health-worker@{1..N}`, `-dev` | 〃 | 워커가 재시작되지 않음 |
| `stackhealth_app` | nginx upstream **블록 이름**. `deploy.sh`가 생성하고 서버 블록의 `proxy_pass`가 이 이름을 가리킨다 | 502 |
| `/usr/local/bin/stackhealth-nginx-switch` | `deploy.sh:125`가 `sudo`로 호출하는 전환 래퍼 (NOPASSWD 등록됨, repo에 없는 호스트 전용 파일) | 배포 중 슬롯 전환 불가 |
| `/etc/nginx/conf.d/stackhealth-upstream.conf` | 위 래퍼가 갱신하는, 실제 nginx가 읽는 파일 | 502 (장애 이력 참고) |
| `/tmp/stackhealth-deploy.lock` | 동시 배포 방지 flock 대상 | 배포 두 개가 겹칠 수 있음 |
| `stack_health_dev` | dev DB 이름 (`.env.dev`) | dev 마이그레이션 실패 |
| `com.stackhealth.app` | Android 패키지 ID (Play 스토어 등록값) | **별개 앱 취급 — 기존 사용자가 업데이트를 못 받음** |
| `mobile/pubspec.yaml`의 `name: stack_health` | Dart 패키지 이름, 앱 내부 import 경로 | 빌드 실패 |
| `server.stackhealth.life` | Redis 호스트. 실제 값은 서버 `worker/.env`의 `REDIS_URL`(저장소에 없음) | 워커가 Redis에 연결 못 함 |

이름을 정말 정리하고 싶다면 **서버를 새로 구축할 때**가 자연스러운 시점이다. 돌아가는 서버에서 위 항목을 동시에 바꾸는 것은 되돌리기 어렵고 얻는 것이 없다.

한편 **웹 도메인**(`stackhealth.life` → `story.onebitebitcoin.com`)은 사용자에게 보이므로 전환 대상이며, 절차는 `docs/DOMAIN-CUTOVER.md`에 있다.

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

배포 시에는 `deploy.sh`가 두 파일을 모두 갱신한다 (`scripts/deploy.sh` Step 7). 다만 실제 nginx 설정은 **직접 쓰지 않고** `sudo /usr/local/bin/stackhealth-nginx-switch <포트>`(NOPASSWD 등록된 호스트 전용 래퍼)를 호출하고, repo의 `nginx/upstream.conf`는 그 뒤에 참조용으로 덮어쓴다.

### 파괴적 마이그레이션 — expand/contract (MANDATORY)

> **구 코드가 쓰던 것을 없애는 마이그레이션(DROP TABLE/COLUMN, NOT NULL 추가, 컬럼 rename)은 배포 창에서 장애를 만든다.**

두 슬롯은 같은 DB를 본다. `deploy.sh`가 마이그레이션을 올린 뒤 구 슬롯이 죽기까지
수십 초~1분 동안, **nginx는 아직 구 슬롯으로 트래픽을 보낸다.** 그 사이 구 코드가
사라진 테이블을 조회하면 500이 난다. 업로드는 ffmpeg 처리를 다 끝낸 뒤 마지막
저장에서 깨져 사용자가 결과물을 잃는다.

그래서 마이그레이션을 성격으로 가른다.

| | 무엇 | 언제 |
|---|---|---|
| **expand** | 구 코드가 봐도 안전 — ADD COLUMN(nullable), 데이터 이동, 인덱스 추가 | 슬롯 기동 **전** (Step 4) |
| **contract** | 구 코드가 쓰던 것 제거 — DROP, rename, NOT NULL 추가 | 구 슬롯 종료 **후** (Step 7) |

**하는 법**

1. 마이그레이션 체인에서 **contract를 맨 뒤로** 둔다. 중간에 있으면 expand까지
   올리려다 contract를 거치게 된다.
2. `backend/alembic/EXPAND_TARGET`에 **expand의 마지막 리비전**을 적는다.
   `deploy.sh`가 Step 4에서 거기까지만 올리고, 나머지는 Step 7에서 올린다.
3. **배포가 끝나면 그 파일을 지운다.** 남겨두면 다음 배포가 그 리비전에서 멈춰
   새 마이그레이션이 조용히 적용되지 않는다.

파일이 없으면 지금까지처럼 head까지 한 번에 올린다 — 파괴적 변경이 없는 평소
배포는 아무것도 달라지지 않는다.

> **전부 뒤로 미루면 안 된다.** 새 코드가 필요로 하는 컬럼(ADD COLUMN)까지 미루면
> 새 슬롯이 그 컬럼 없이 떠서 더 크게 깨진다. 확장은 앞, 수축은 뒤다.

### 워커(worker) 멀티 인스턴스 — 핵심 주의사항

**실제 운영 워커**: `measly` 유저 systemd `--user` 템플릿 유닛 `stack-health-worker@1`, `stack-health-worker@2` (`~/.config/systemd/user/stack-health-worker@.service`, repo에는 없음 — 다른 `stack-health-app-*` 유닛들과 동일하게 호스트 전용 파일). `WorkingDirectory=/home/measly/stack-health/worker`에서 repo 코드를 직접 실행한다.

- 인스턴스 개수는 `worker/.env`의 `WORKER_INSTANCES`로 정하고, `scripts/deploy.sh`가 이 값을 읽어 `stack-health-worker@1..N`을 전부 재시작한다 (push 배포 시 자동).
- `backend/app/services/cartoon.py`, `muscle_heat.py`의 `_worker_pool_size()`는 **`FFMPEG_ACTIVE_JOBS`**(worker.py가 렌더 시작 직전 `ffmpeg:slots` 리스 점유 수로 매 잡마다 주입하는 실시간 활성 잡 수)로 코어 예산을 나눠 프로세스 풀 크기를 정한다 — 잡이 1개뿐이면 코어 예산을 다 쓰고, 여러 잡이 겹치면 나눠 쓴다. `WORKER_INSTANCES`는 `FFMPEG_ACTIVE_JOBS`가 없을 때(단독 실행·테스트)만 쓰는 폴백이라 **정적 상한이 아니다** — 기본 8코어 기준 프로세스 풀은 잡 1개면 `(8-2)/1=6`, 잡 2개가 겹치면 `(8-2)/2=3`으로 실시간으로 바뀐다. 두 값(`FFMPEG_ACTIVE_JOBS` 키 이름)이 `worker/worker.py`(설정)와 두 backend 모듈(사용) 양쪽에 문자열로 하드코딩돼 있어, 한쪽만 고치면 조용히 `WORKER_INSTANCES` 폴백으로 흡수되고 에러 없이 성능만 저하된다 — 변경 시 둘 다 확인.
- 워커 전용 배포 스크립트는 **없다**. push 배포 하나로 앱과 함께 나간다. (`/opt/stackhealth-worker` 단일 전용서버 배포용 문서·스크립트가 예전에 `worker/`에 있었는데, 실행되지 않는 경로라 `archive-meta/worker-opt/`로 옮겼다.)

### 장애 이력 (2026-05-31)

- **증상**: `https://stackhealth.life` 전체 502/521, 데이터가 보이지 않음
- **원인**: deploy.sh가 `/etc/nginx/conf.d/stackhealth-upstream.conf`를 8018로 바꿨으나 green 슬롯이 실행되지 않았음. DB/백엔드 자체는 정상이었음.
- **해결**: `/etc/nginx/conf.d/stackhealth-upstream.conf`를 8017(blue)로 수정 후 reload
- **재발 방지**: `deploy.sh` Step 7이 실제 nginx 설정 파일을 직접 업데이트하도록 수정 완료
