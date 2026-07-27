import os
import sys

from dotenv import load_dotenv

load_dotenv()

REDIS_URL: str = os.environ["REDIS_URL"]
DATABASE_URL: str = os.environ["DATABASE_URL"]
R2_ACCOUNT_ID: str = os.environ["R2_ACCOUNT_ID"]
R2_ACCESS_KEY_ID: str = os.environ["R2_ACCESS_KEY_ID"]
R2_SECRET_ACCESS_KEY: str = os.environ["R2_SECRET_ACCESS_KEY"]
R2_BUCKET_NAME: str = os.environ["R2_BUCKET_NAME"]
R2_PUBLIC_URL: str = os.environ["R2_PUBLIC_URL"].rstrip("/")
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
ENVIRONMENT: str = os.environ.get("ENVIRONMENT", "production")
QUEUE_NAME: str = f"queue:merge-jobs:{ENVIRONMENT}"
JOB_TTL: int = 86400  # 24시간
MAX_FFMPEG_CONCURRENT: int = int(os.environ.get("MAX_FFMPEG_CONCURRENT", "2"))
MAX_JOB_RETRIES: int = int(os.environ.get("MAX_JOB_RETRIES", "2"))
# 동시에 띄우는 worker.py 인스턴스 수 — cartoon.py/muscle_heat.py가 이 값으로 job당
# 내부 프로세스 풀 크기를 나눠 8코어 과다구독을 막는다 (WORKER_INSTANCES개 인스턴스가
# 동시에 무거운 job을 처리해도 총 프로세스 수가 코어 수를 넘지 않도록).
WORKER_INSTANCES: int = int(os.environ.get("WORKER_INSTANCES", "1"))

_backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend"))
if os.path.isdir(_backend_path) and _backend_path not in sys.path:
    sys.path.insert(0, _backend_path)
