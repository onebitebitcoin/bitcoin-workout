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
    bash "$TELEGRAM_SCRIPT" "❌ <b>Orange Story 배포 실패</b>
🕐 ${NOW} (KST)
• 배포 슬롯: ${NEXT_SLOT:-unknown} (포트 ${NEXT_PORT:-?})
• 실패 코드: ${EXIT_CODE}
• 현재 슬롯 유지: ${CURRENT_SLOT:-unknown}" 2>/dev/null || true
}
trap '_notify_fail' ERR

# ── 동시 배포 방지 (배타 잠금) ────────────────────────────────────────
# 배포 두 개가 겹치면 한쪽의 npm ci가 node_modules를 지우는 중에 다른 쪽이
# 설치를 끝내 의존성 트리가 깨진 채 exit 0이 된다.
# (2026-07-28 v0.17.3~0.17.5 배포 3연속 실패 — "tsc: not found" 원인)
LOCK_FILE="/tmp/stackhealth-deploy.lock"
LOCK_WAIT=600
exec 200>"$LOCK_FILE"
if ! flock -w "$LOCK_WAIT" 200; then
    echo "✗ 다른 배포가 ${LOCK_WAIT}초 넘게 진행 중 → 이번 배포 중단"
    bash "$TELEGRAM_SCRIPT" "⏳ <b>Orange Story 배포 중단</b>
🕐 $(TZ="Asia/Seoul" date "+%Y-%m-%d %H:%M") (KST)
• 다른 배포가 진행 중이어서 잠금 획득 실패 (${LOCK_WAIT}초 대기)" 2>/dev/null || true
    exit 1
fi

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
echo "║  Orange Story Blue-Green 배포             ║"
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

# ── Step 4: DB 마이그레이션 — expand 단계 ────────────────────────────
# 이 시점에는 구 슬롯이 아직 nginx 트래픽을 받고 있고 두 슬롯이 같은 DB 를 본다.
# 그래서 여기서는 "구 코드가 봐도 안전한" 변경만 올린다 (ADD COLUMN, 데이터 이동).
# 구 코드가 쓰던 것을 없애는 변경(DROP TABLE/COLUMN)은 구 슬롯이 죽은 뒤(Step 7-2)로
# 미룬다 — expand/contract 패턴.
#
# EXPAND_TARGET 파일이 있으면 그 리비전까지만 올리고, 없으면 지금까지처럼 head 까지
# 한 번에 올린다(대부분의 배포는 파괴적 변경이 없으므로 파일이 없다).
EXPAND_FILE="$APP_DIR/backend/alembic/EXPAND_TARGET"
if [ -f "$EXPAND_FILE" ]; then
    EXPAND_TARGET=$(grep -v '^[[:space:]]*#' "$EXPAND_FILE" | tr -d '[:space:]' | head -1)
fi
EXPAND_TARGET="${EXPAND_TARGET:-head}"

if [ "$EXPAND_TARGET" = "head" ]; then
    echo "[4/8] DB 마이그레이션..."
else
    echo "[4/8] DB 마이그레이션 — expand ($EXPAND_TARGET 까지)..."
    echo "      나머지는 이전 슬롯 종료 후 적용된다 (EXPAND_TARGET 파일 참고)"
fi
cd backend && .venv/bin/alembic upgrade "$EXPAND_TARGET"
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

# ── DB 마이그레이션 — contract 단계 ──────────────────────────────────
# 구 슬롯이 죽었으므로 이제 구 코드가 쓰던 것을 없애도 안전하다.
# expand 에서 head 까지 이미 올렸으면(EXPAND_TARGET 파일 없음) 할 일이 없다.
if [ "$EXPAND_TARGET" != "head" ]; then
    echo "    DB 마이그레이션 — contract (head 까지)..."
    if (cd backend && .venv/bin/alembic upgrade head); then
        cd "$APP_DIR"
        echo "    ✓ contract 마이그레이션 완료"
    else
        cd "$APP_DIR"
        echo ""
        echo "⚠️  contract 마이그레이션 실패"
        echo "    서비스는 새 슬롯($NEXT_SLOT)으로 이미 전환됐고 정상 동작한다 —"
        echo "    새 코드는 contract 대상(예: 삭제될 테이블)을 참조하지 않기 때문이다."
        echo "    수동으로 확인 후 실행한다: cd backend && .venv/bin/alembic upgrade head"
        bash "$TELEGRAM_SCRIPT" "⚠️ <b>Orange Story contract 마이그레이션 실패</b>
🕐 $(TZ="Asia/Seoul" date "+%Y-%m-%d %H:%M") (KST)
• 서비스는 정상 (새 슬롯 ${NEXT_SLOT} 전환 완료)
• 수동 실행 필요: cd backend && .venv/bin/alembic upgrade head" 2>/dev/null || true
    fi
fi

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
