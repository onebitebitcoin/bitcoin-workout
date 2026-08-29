# Orange Story Video Worker

Redis 큐 기반 ffmpeg 비디오+오디오 병합 워커.

## 설치

### Mac
```bash
brew install ffmpeg
cd worker/
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### Ubuntu
```bash
sudo apt update && sudo apt install -y ffmpeg
cd worker/
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## 환경변수 설정

```bash
cp .env.example .env
# .env 파일에서 Redis URL 및 R2 크레덴셜 입력
```

| 변수 | 설명 |
|------|------|
| `REDIS_URL` | Redis 접속 URL (예: `redis://localhost:6379/0` 또는 Upstash URL) |
| `R2_ACCOUNT_ID` | Cloudflare R2 계정 ID |
| `R2_ACCESS_KEY_ID` | R2 액세스 키 |
| `R2_SECRET_ACCESS_KEY` | R2 시크릿 키 |
| `R2_BUCKET_NAME` | R2 버킷 이름 |
| `R2_PUBLIC_URL` | R2 퍼블릭 CDN URL |
| `LOG_LEVEL` | 로그 레벨 (기본: `INFO`) |

## 실행

```bash
bash start.sh
```

또는 수동 실행:
```bash
python health_check.py   # 연결 확인
python worker.py         # 워커 시작
```

## 동작 방식

1. 백엔드가 `queue:merge-jobs` Redis 리스트에 잡 페이로드를 LPUSH
2. 워커가 BRPOP으로 잡을 꺼내 처리
3. R2에서 video/audio 다운로드 → ffmpeg 병합 → R2에 업로드
4. 잡 상태를 `job:{job_id}` Redis Hash에 기록 (TTL 24시간)

## 잡 상태 확인

```bash
redis-cli hgetall job:<job_id>
```

상태값: `pending` → `processing` → `completed` | `failed`

## 테스트

```bash
# Redis에 테스트 잡 직접 주입
python -c "
from queue_client import get_redis_client, enqueue_job
r = get_redis_client()
job_id = enqueue_job(r, {
    'user_id': 1,
    'video_r2_key': 'videos/test.mp4',
    'audio_r2_key': 'audio/test.webm',
    'audio_duration_sec': 10,
    'audio_content_type': 'audio/webm',
})
print('Enqueued job:', job_id)
"
```
