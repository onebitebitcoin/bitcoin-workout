#!/bin/bash
# Bitcoiners Video Worker - Ubuntu 배포 스크립트
# 도메인: server.stackhealth.life
# 사용법: sudo bash deploy.sh
#
# 전제 조건:
# - Ubuntu 22.04 LTS
# - 이 스크립트를 worker/ 디렉토리에서 실행
# - .env 파일이 준비되어 있거나 REDIS_URL 등 환경변수를 알고 있어야 함

set -e

INSTALL_DIR="/opt/stackhealth-worker"
SERVICE_USER="stackhealth"
SERVICE_NAME="stackhealth-worker"
# 동시에 띄울 worker.py 인스턴스 수 — 환경변수로 오버라이드 가능 (예: WORKER_INSTANCES=2 bash deploy.sh)
# cartoon.py/muscle_heat.py가 이 값을 .env에서 읽어 job당 내부 프로세스 풀 크기를 나눈다.
WORKER_INSTANCES="${WORKER_INSTANCES:-1}"

echo "======================================"
echo " Bitcoiners Worker 배포 시작"
echo " 설치 경로: $INSTALL_DIR"
echo "======================================"

# ── 1. 시스템 패키지 설치 ──────────────────────────────────────────
echo "[1/7] 시스템 패키지 설치..."
apt-get update -qq
apt-get install -y -qq \
    python3 python3-pip python3-venv \
    ffmpeg \
    redis-server \
    curl

# ffmpeg 버전 확인
ffmpeg -version 2>&1 | head -1

# ── 2. Redis 설정 (로컬) ──────────────────────────────────────────
echo "[2/7] Redis 설정..."

# Redis 비밀번호 생성 (없으면)
REDIS_PASSWORD_FILE="/etc/stackhealth-redis-password"
if [ ! -f "$REDIS_PASSWORD_FILE" ]; then
    REDIS_PASS=$(openssl rand -hex 24)
    echo "$REDIS_PASS" > "$REDIS_PASSWORD_FILE"
    chmod 600 "$REDIS_PASSWORD_FILE"
    echo "  → Redis 비밀번호 생성됨: $REDIS_PASS"
else
    REDIS_PASS=$(cat "$REDIS_PASSWORD_FILE")
    echo "  → 기존 Redis 비밀번호 사용"
fi

# Redis 외부 접속 허용 + 인증 설정
REDIS_CONF="/etc/redis/redis.conf"
# bind를 0.0.0.0으로 (외부 접속 허용 - firewall로 보호)
sed -i 's/^bind 127.0.0.1.*/bind 0.0.0.0/' "$REDIS_CONF"
# 비밀번호 설정
if grep -q "^requirepass" "$REDIS_CONF"; then
    sed -i "s/^requirepass.*/requirepass $REDIS_PASS/" "$REDIS_CONF"
else
    echo "requirepass $REDIS_PASS" >> "$REDIS_CONF"
fi

systemctl restart redis-server
systemctl enable redis-server

REDIS_URL="redis://:${REDIS_PASS}@server.stackhealth.life:6379/0"
echo "  → Redis URL: $REDIS_URL"

# ── 3. 서비스 사용자 생성 ─────────────────────────────────────────
echo "[3/7] 서비스 사용자 생성..."
useradd -r -s /bin/false "$SERVICE_USER" 2>/dev/null && \
    echo "  → 사용자 $SERVICE_USER 생성됨" || \
    echo "  → 사용자 $SERVICE_USER 이미 존재"

# ── 4. 워커 파일 설치 ─────────────────────────────────────────────
echo "[4/7] 워커 파일 설치..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$INSTALL_DIR"
cp -r "$SCRIPT_DIR"/. "$INSTALL_DIR/"
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

# ── 5. Python 가상환경 및 의존성 ──────────────────────────────────
echo "[5/7] Python 의존성 설치..."
sudo -u "$SERVICE_USER" python3 -m venv "$INSTALL_DIR/venv"
sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"

# ── 6. 환경변수 파일 설정 ─────────────────────────────────────────
echo "[6/7] 환경변수 설정..."
ENV_FILE="$INSTALL_DIR/.env"

if [ ! -f "$ENV_FILE" ] || [ ! -s "$ENV_FILE" ]; then
    # .env.example 복사 후 Redis URL 자동 주입
    cp "$INSTALL_DIR/.env.example" "$ENV_FILE"
    # Redis URL을 위에서 생성한 값으로 교체
    sed -i "s|REDIS_URL=.*|REDIS_URL=$REDIS_URL|" "$ENV_FILE"
    sed -i "s|WORKER_INSTANCES=.*|WORKER_INSTANCES=$WORKER_INSTANCES|" "$ENV_FILE"
    chown "$SERVICE_USER:$SERVICE_USER" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    echo ""
    echo "  ⚠️  환경변수 파일을 편집해서 R2 크레덴셜을 설정하세요:"
    echo "     nano $ENV_FILE"
    echo ""
    echo "  필수 항목:"
    grep -E "^(R2_|REDIS_)" "$ENV_FILE"
    echo ""
else
    echo "  → 기존 .env 파일 유지 (WORKER_INSTANCES는 값이 있으면 갱신)"
    if grep -q "^WORKER_INSTANCES=" "$ENV_FILE"; then
        sed -i "s|^WORKER_INSTANCES=.*|WORKER_INSTANCES=$WORKER_INSTANCES|" "$ENV_FILE"
    else
        echo "WORKER_INSTANCES=$WORKER_INSTANCES" >> "$ENV_FILE"
    fi
fi

# ── 7. systemd 서비스 설치 (템플릿 유닛, 인스턴스 N개) ─────────────
echo "[7/7] systemd 서비스 설치 (인스턴스 ${WORKER_INSTANCES}개)..."
cp "$INSTALL_DIR/stackhealth-worker@.service" /etc/systemd/system/
# 예전 단일 유닛(stackhealth-worker.service)이 남아있으면 정리 — 템플릿 유닛으로 대체됨
if systemctl list-unit-files "${SERVICE_NAME}.service" &>/dev/null; then
    systemctl disable --now "${SERVICE_NAME}.service" 2>/dev/null || true
    rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
fi
systemctl daemon-reload
for i in $(seq 1 "$WORKER_INSTANCES"); do
    systemctl enable "${SERVICE_NAME}@${i}"
done

echo ""
echo "======================================"
echo " 배포 완료"
echo "======================================"
echo ""
echo "다음 단계:"
echo "  1. R2 크레덴셜 설정:  nano $ENV_FILE"
echo "  2. 헬스체크:          sudo -u $SERVICE_USER $INSTALL_DIR/venv/bin/python $INSTALL_DIR/health_check.py"
echo "  3. 워커 시작 (인스턴스 ${WORKER_INSTANCES}개):"
for i in $(seq 1 "$WORKER_INSTANCES"); do
    echo "       systemctl start ${SERVICE_NAME}@${i}"
done
echo "  4. 로그 확인:         journalctl -u '${SERVICE_NAME}@*' -f"
echo ""
echo "Railway 백엔드에 설정할 REDIS_URL:"
echo "  $REDIS_URL"
echo ""
echo "방화벽 설정 (ufw 사용 시):"
echo "  ufw allow 6379/tcp   # Railway에서 Redis 접속용"
echo "  ufw allow 22/tcp     # SSH"
echo "  ufw enable"
echo ""
