# Bitcoiners Worker - 배포 가이드

> LLM이 읽고 배포/운영/트러블슈팅을 수행할 수 있도록 작성된 가이드입니다.

---

## 시스템 아키텍처

```
[브라우저]
    │ POST /api/v1/videos/merge-audio (영상+오디오)
    ▼
[FastAPI 백엔드]
    │ 1) audio를 R2에 업로드
    │ 2) Redis LPUSH queue:merge-jobs {job_id, ...}
    │    └─ Redis 불가 시 → 백엔드에서 직접 ffmpeg 처리 (fallback)
    │       ⚠️ fallback은 in-memory (_local_jobs dict)로 상태 저장
    │       ⚠️ 재배포/멀티 인스턴스 시 fallback 잡 상태 소실됨
    │       ⚠️ 프로덕션에서는 반드시 Redis 연결 유지 권장
    │ 3) job_id 즉시 반환
    ▼
[브라우저 - 3초 간격 폴링]
    │ GET /api/v1/videos/merge-job/{job_id}
    ▼
[Redis - job:{job_id} Hash]
    └─ status: pending → processing → completed | failed
    └─ output_r2_key, cdn_url (completed 시)

[Ubuntu Worker - server.stackhealth.life]
    - Redis BRPOP queue:merge-jobs (5초 타임아웃 루프)
    - R2에서 video, audio 다운로드
    - ffmpeg 병합
    - 결과를 R2 업로드
    - Redis HSET job:{job_id} status=completed ...
```

---

## 파일 구조

```
worker/
├── worker.py               # 메인 루프 (BRPOP + 잡 처리)
├── tasks/
│   └── merge.py            # ffmpeg 병합 로직
├── queue_client.py         # Redis API (enqueue/dequeue/status)
├── config.py               # 환경변수 로드
├── health_check.py         # Redis + R2 연결 확인
├── requirements.txt        # Python 의존성
├── .env.example            # 환경변수 템플릿
├── deploy.sh               # Ubuntu 원클릭 배포 스크립트
├── stackhealth-worker.service  # systemd 서비스 정의
└── DEPLOY.md               # 이 파일
```

---

## 환경변수

| 변수 | 필수 | 설명 | 예시 |
|------|------|------|------|
| `REDIS_URL` | ✅ | Redis 연결 URL | `redis://:password@server.stackhealth.life:6379/0` |
| `R2_ACCOUNT_ID` | ✅ | Cloudflare 계정 ID | `abc123def456` |
| `R2_ACCESS_KEY_ID` | ✅ | R2 Access Key | `xxxxx` |
| `R2_SECRET_ACCESS_KEY` | ✅ | R2 Secret Key | `xxxxx` |
| `R2_BUCKET_NAME` | ✅ | R2 버킷 이름 | `stackhealth-videos` |
| `R2_PUBLIC_URL` | ✅ | R2 공개 URL | `https://pub-xxx.r2.dev` |
| `LOG_LEVEL` | ❌ | 로그 레벨 (기본: INFO) | `DEBUG` |

백엔드에도 동일한 `REDIS_URL`을 설정해야 함.

---

## Ubuntu 서버 초기 배포

### 전제 조건
- Ubuntu 22.04 LTS
- root 또는 sudo 권한
- 도메인 `server.stackhealth.life`이 서버 IP를 가리키고 있음

### 배포 절차

```bash
# 1. 워커 코드를 서버로 복사
scp -r ./worker/ root@server.stackhealth.life:/tmp/stackhealth-worker/

# 2. 서버에 SSH 접속
ssh root@server.stackhealth.life

# 3. 배포 스크립트 실행 (자동으로 ffmpeg, Redis, Python venv 설치)
cd /tmp/stackhealth-worker
sudo bash deploy.sh

# 4. R2 크레덴셜 설정
nano /opt/stackhealth-worker/.env
# → R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY,
#   R2_BUCKET_NAME, R2_PUBLIC_URL 값 입력

# 5. 헬스체크 실행
sudo -u stackhealth /opt/stackhealth-worker/venv/bin/python /opt/stackhealth-worker/health_check.py

# 6. 워커 시작
systemctl start stackhealth-worker

# 7. 상태 확인
systemctl status stackhealth-worker
journalctl -u stackhealth-worker -f
```

### 배포 스크립트가 자동으로 하는 것
- `ffmpeg`, `python3`, `redis-server` 설치
- Redis 비밀번호 자동 생성 (`/etc/stackhealth-redis-password`에 저장)
- Redis 외부 접속 허용 설정
- `stackhealth` 서비스 계정 생성
- `/opt/stackhealth-worker/`에 파일 설치
- Python venv + 의존성 설치
- systemd 서비스 등록 및 자동시작 설정

---

## 백엔드 환경변수 추가

배포 완료 후 백엔드 환경변수에 추가:

```
REDIS_URL=redis://:비밀번호@server.stackhealth.life:6379/0
```

비밀번호 확인 명령:
```bash
ssh root@server.stackhealth.life cat /etc/stackhealth-redis-password
```

---

## Fallback 동작

`REDIS_URL` 미설정 또는 Redis 연결 불가 시:
- 백엔드가 직접 ffmpeg 처리 (CPU 부하 있음)
- 프론트엔드는 동일하게 job_id로 폴링
- 로그에 `[fallback]` 키워드로 확인 가능

```
[fallback] Redis 없음 — job=xxx 로컬 처리 시작
[fallback] job=xxx: R2에서 video 다운로드
[fallback] job=xxx: 완료 https://...
```

---

## 운영 명령어

### 워커 관리
```bash
systemctl status stackhealth-worker    # 상태 확인
systemctl start stackhealth-worker     # 시작
systemctl stop stackhealth-worker      # 정지
systemctl restart stackhealth-worker   # 재시작
journalctl -u stackhealth-worker -f    # 실시간 로그
journalctl -u stackhealth-worker --since "1 hour ago"  # 최근 1시간
```

### Redis 점검
```bash
redis-cli -a $(cat /etc/stackhealth-redis-password)

# 큐 대기 중인 잡 수
LLEN queue:merge-jobs

# 특정 잡 상태 확인
HGETALL job:{job_id}

# 최근 완료된 잡 목록 (키 패턴)
KEYS job:*

# 큐 비우기 (긴급 시)
DEL queue:merge-jobs
```

### 헬스체크
```bash
sudo -u stackhealth /opt/stackhealth-worker/venv/bin/python /opt/stackhealth-worker/health_check.py
# OK: Redis ping OK, R2 연결 OK
# FAIL: 에러 메시지 + exit 1
```

---

## 트러블슈팅

### 워커가 잡을 처리하지 않는 경우

1. 워커 실행 여부 확인:
   ```bash
   systemctl status stackhealth-worker
   ```

2. 로그 확인:
   ```bash
   journalctl -u stackhealth-worker -n 50
   ```

3. Redis 연결 확인:
   ```bash
   redis-cli -a $(cat /etc/stackhealth-redis-password) ping
   # → PONG 이면 정상
   ```

4. 큐에 잡이 있는지 확인:
   ```bash
   redis-cli -a $(cat /etc/stackhealth-redis-password) LLEN queue:merge-jobs
   ```

### ffmpeg 없다는 오류

```bash
which ffmpeg  # 경로 확인
apt-get install -y ffmpeg  # 재설치
```

### R2 인증 실패

`.env` 파일의 R2 크레덴셜 재확인:
```bash
cat /opt/stackhealth-worker/.env
```

Cloudflare 대시보드 → R2 → Manage API Tokens에서 토큰 권한 확인 (Object Read & Write 필요).

### Redis 외부 접속 불가

1. Redis 설정 확인:
   ```bash
   grep "^bind\|^requirepass" /etc/redis/redis.conf
   # bind 0.0.0.0 이어야 외부 접속 가능
   ```

2. 방화벽 확인:
   ```bash
   ufw status
   # 6379/tcp ALLOW 이어야 함
   ufw allow 6379/tcp
   ```

3. 포트 열려있는지 확인:
   ```bash
   ss -tlnp | grep 6379
   ```

4. 원격에서 연결 테스트:
   ```bash
   redis-cli -h server.stackhealth.life -a 비밀번호 ping
   ```

### 잡이 processing 상태에서 멈춘 경우

워커가 재시작되면 in-memory 상태가 초기화되어 해당 잡은 복구 불가.
프론트엔드는 120초(40회 × 3초) 폴링 후 자동으로 원본 영상 사용.

---

## 업데이트 배포

```bash
# 로컬에서 변경사항 서버에 반영
scp -r ./worker/ root@server.stackhealth.life:/tmp/stackhealth-worker-new/
ssh root@server.stackhealth.life

# 워커 정지 → 파일 교체 → 재시작
systemctl stop stackhealth-worker
cp -r /tmp/stackhealth-worker-new/. /opt/stackhealth-worker/
chown -R stackhealth:stackhealth /opt/stackhealth-worker
# .env는 덮어쓰지 않음 (기존 유지)
/opt/stackhealth-worker/venv/bin/pip install --quiet -r /opt/stackhealth-worker/requirements.txt
systemctl start stackhealth-worker
journalctl -u stackhealth-worker -f
```

---

## 보안 체크리스트

- [ ] Redis 비밀번호 설정 확인 (`requirepass`)
- [ ] ufw로 6379 포트를 백엔드 서버 IP만 허용
- [ ] `.env` 파일 권한 600 확인: `ls -la /opt/stackhealth-worker/.env`
- [ ] Redis 비밀번호 파일 권한 600 확인: `ls -la /etc/stackhealth-redis-password`
- [ ] R2 크레덴셜이 git에 포함되지 않음 확인

---

## Redis 외부 서비스 대안 (Upstash)

Ubuntu Redis 대신 [Upstash](https://upstash.com) 무료 플랜 사용 가능:
- 무료: 10,000 commands/day (소규모 서비스에 충분)
- TLS 기본 지원 (보안 설정 불필요)

설정 방법:
1. https://console.upstash.com 에서 Redis 생성
2. "Redis URL" 복사 (rediss:// 로 시작하는 TLS URL)
3. `.env`와 백엔드 환경변수에 동일한 URL 설정
4. deploy.sh 실행 시 Redis 설치/설정 과정 건너뜀
