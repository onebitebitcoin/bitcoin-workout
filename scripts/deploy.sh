#!/bin/bash
# Blue-Green 무중단 배포 스크립트
# 사용법: ./scripts/deploy.sh
set -e

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SLOT_FILE="$APP_DIR/.deploy-slot"
NGINX_UPSTREAM="$APP_DIR/nginx/upstream.conf"

export XDG_RUNTIME_DIR=/run/user/$(id -u)
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus

TELEGRAM_SCRIPT="/home/measly/.claude/scripts/telegram-send.sh"
_notify_fail() {
    local EXIT_CODE=$?
    local NOW
    NOW=$(TZ="Asia/Seoul" date "+%Y-%m-%d %H:%M")
    bash "$TELEGRAM_SCRIPT" "❌ <b>Stack Health 배포 실패</b>
🕐 ${NOW} (KST)
• 배포 슬롯: ${NEXT_SLOT:-unknown} (포트 ${NEXT_PORT:-?})
• 실패 코드: ${EXIT_CODE}
• 현재 슬롯 유지: ${CURRENT_SLOT:-unknown}" 2>/dev/null || true
}
trap '_notify_fail' ERR

# ── 현재/다음 슬롯 결정 ───────────────────────────────────────────────
CURRENT_SLOT=$(cat "$SLOT_FILE" 2>/dev/null || echo "blue")
if [ "$CURRENT_SLOT" = "blue" ]; then
    NEXT_SLOT="green"
    NEXT_PORT=8018
    CURRENT_PORT=8017
else
    NEXT_SLOT="blue"
    NEXT_PORT=8017
    CURRENT_PORT=8018
fi

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  Stack Health Blue-Green 배포             ║"
echo "╠══════════════════════════════════════════╣"
echo "║  현재: $CURRENT_SLOT (포트 $CURRENT_PORT)              ║"
echo "║  배포: $NEXT_SLOT (포트 $NEXT_PORT)               ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── Step 1: 코드 업데이트 ─────────────────────────────────────────────
echo "[1/8] git pull..."
cd "$APP_DIR"
git restore nginx/upstream.conf 2>/dev/null || true
git pull --rebase origin main

# ── Step 2: 의존성 설치 ───────────────────────────────────────────────
echo "[2/8] 백엔드 의존성 설치..."
backend/.venv/bin/pip install --quiet -r backend/requirements.txt
# opencv-contrib-python(GUI 포함) 충돌 방지 — backend/requirements.txt 주석 참고
backend/.venv/bin/pip install --quiet --no-deps mediapipe==0.10.35

echo "      워커 의존성 설치..."
worker/.venv/bin/pip install --quiet -r worker/requirements.txt
worker/.venv/bin/pip install --quiet --no-deps mediapipe==0.10.35

# ── Step 3: 프론트엔드 빌드 ───────────────────────────────────────────
echo "[3/8] 프론트엔드 빌드..."
set -a; source "$APP_DIR/.env"; set +a
cd frontend && npm ci --silent && npm run build
cd "$APP_DIR"

# ── Step 4: DB 마이그레이션 (idempotent) ─────────────────────────────
echo "[4/8] DB 마이그레이션..."
cd backend && .venv/bin/alembic upgrade head
cd "$APP_DIR"

# ── Step 5: 다음 슬롯 기동 ───────────────────────────────────────────
echo "[5/8] $NEXT_SLOT 슬롯 기동 (포트 $NEXT_PORT)..."
systemctl --user restart "stack-health-app-$NEXT_SLOT"

# ── Step 6: 헬스체크 ─────────────────────────────────────────────────
echo "[6/8] 헬스체크 대기 (최대 60초)..."
MAX_WAIT=60
INTERVAL=2
ELAPSED=0
HEALTH_STATUS=""

while [ $ELAPSED -lt $MAX_WAIT ]; do
    HEALTH_STATUS=$(curl -sf "http://127.0.0.1:$NEXT_PORT/health" 2>/dev/null \
        | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null \
        || echo "")
    if [ "$HEALTH_STATUS" = "ok" ]; then
        echo "    ✓ 헬스체크 통과 (${ELAPSED}초)"
        break
    fi
    printf "    대기중... %d초\r" "$ELAPSED"
    sleep $INTERVAL
    ELAPSED=$((ELAPSED + INTERVAL))
done

if [ "$HEALTH_STATUS" != "ok" ]; then
    echo ""
    echo "✗ 헬스체크 실패 → 롤백"
    systemctl --user stop "stack-health-app-$NEXT_SLOT" || true
    echo "  현재 슬롯($CURRENT_SLOT, 포트 $CURRENT_PORT)은 계속 운영 중"
    exit 1
fi

# ── Step 7: Nginx 전환 + 이전 슬롯 종료 ──────────────────────────────
echo "[7/8] Nginx upstream 전환 → $NEXT_SLOT (포트 $NEXT_PORT)..."

# nginx upstream 전환 + reload (NOPASSWD 스크립트 사용)
sudo /usr/local/bin/stackhealth-nginx-switch "$NEXT_PORT"

# repo 파일도 동기화 (참조용)
cat > "$NGINX_UPSTREAM" << EOF
upstream stackhealth_app {
    server 127.0.0.1:$NEXT_PORT;
    keepalive 32;
}
EOF

echo "    ✓ Nginx reload 완료 (무중단)"

# 인플라이트 요청 처리 대기 후 이전 슬롯 종료
sleep 5
echo "    이전 슬롯 종료 ($CURRENT_SLOT, 포트 $CURRENT_PORT)..."
systemctl --user stop "stack-health-app-$CURRENT_SLOT" || true

# 슬롯 파일 업데이트
echo "$NEXT_SLOT" > "$SLOT_FILE"

# 워커 재시작 (WORKER_INSTANCES개 인스턴스 — worker/.env 기준, systemd 템플릿 유닛 stack-health-worker@N)
WORKER_INSTANCES=$(grep "^WORKER_INSTANCES=" "$APP_DIR/worker/.env" 2>/dev/null | cut -d= -f2)
WORKER_INSTANCES="${WORKER_INSTANCES:-1}"
echo "    워커 재시작 (인스턴스 ${WORKER_INSTANCES}개)..."
for i in $(seq 1 "$WORKER_INSTANCES"); do
    systemctl --user restart "stack-health-worker@${i}"
done

echo ""
echo "✅ 배포 완료"
echo "   활성 슬롯: $NEXT_SLOT (포트 $NEXT_PORT)"
echo "   슬롯 파일: $SLOT_FILE"

# ── Step 8: dev(staging) 환경 동기화 (non-fatal) ─────────────────────
# git pull/프론트빌드 결과는 운영과 dev가 같은 backend/static 디렉토리를 공유하므로
# 이미 자동 반영됨. 여기서는 dev DB 마이그레이션 + dev 프로세스 재시작만 수행해
# 메모리에 남은 옛 코드를 갱신한다. 실패해도 운영 배포 결과에는 영향 없음.
echo ""
echo "[8/8] dev 환경 동기화 (dev.stackhealth.life)..."
set +e
(
    set -e
    DEV_DB_URL=$(grep "^DATABASE_URL=" "$APP_DIR/.env.dev" | cut -d= -f2-)
    if [ -n "$DEV_DB_URL" ]; then
        echo "    dev DB 마이그레이션 (stack_health_dev)..."
        cd "$APP_DIR/backend" && DATABASE_URL="$DEV_DB_URL" .venv/bin/alembic upgrade head
        cd "$APP_DIR"
    else
        echo "    ⚠ .env.dev에서 DATABASE_URL 미발견 — dev DB 마이그레이션 건너뜀"
    fi
    echo "    dev 백엔드/워커 재시작..."
    systemctl --user restart stack-health-app-dev
    systemctl --user restart stack-health-worker-dev
)
DEV_RC=$?
set -e
if [ "$DEV_RC" -ne 0 ]; then
    echo "    ⚠ dev 동기화 중 일부 실패 (운영 배포에는 영향 없음)"
    echo "      'journalctl --user -u stack-health-app-dev -u stack-health-worker-dev' 확인"
else
    echo "    ✓ dev 동기화 완료 — https://dev.stackhealth.life 에서 최신 코드 확인 가능"
fi
