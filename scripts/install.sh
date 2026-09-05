#!/bin/bash
set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "=== bitcoin_workout install.sh ==="

# --- OS 감지 및 시스템 패키지 설치 ---
OS="$(uname -s)"
echo "[시스템] OS: $OS"

if [ "$OS" = "Linux" ]; then
  # Ubuntu / Debian
  if command -v apt-get &>/dev/null; then
    echo "[시스템] Ubuntu/Debian 패키지 설치..."
    sudo apt-get update -qq
    sudo apt-get install -y --no-install-recommends \
      ffmpeg \
      python3 python3-pip python3-venv \
      curl
    echo "[시스템] 패키지 설치 완료"
  fi
elif [ "$OS" = "Darwin" ]; then
  # macOS — Homebrew 사용
  if command -v brew &>/dev/null; then
    echo "[시스템] Homebrew 패키지 확인..."
    brew list ffmpeg &>/dev/null || brew install ffmpeg
  else
    echo "[!] Homebrew 미설치 — https://brew.sh 참고"
  fi
fi

# --- Node.js 확인 ---
if ! command -v node &>/dev/null; then
  echo "[!] Node.js 미설치. nvm 또는 https://nodejs.org 에서 설치하세요."
  exit 1
fi
echo "[Node] $(node --version)"

# --- Backend ---
echo "[Backend] Python 가상환경 셋업..."
cd "$PROJECT_ROOT/backend"

PYTHON_BIN="python3"
if ! command -v python3 &>/dev/null; then
  echo "[!] python3 미설치"
  exit 1
fi

if [ ! -d ".venv" ]; then
  $PYTHON_BIN -m venv .venv
  echo "  .venv 생성 완료"
fi
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
echo "[Backend] 의존성 설치 완료 (Python $(python3 --version))"
deactivate

# --- Worker ---
echo "[Worker] Python 가상환경 셋업..."
cd "$PROJECT_ROOT/worker"
if [ ! -d ".venv" ]; then
  $PYTHON_BIN -m venv .venv
  echo "  .venv 생성 완료"
fi
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
echo "[Worker] 의존성 설치 완료"
deactivate

# --- Frontend ---
echo "[Frontend] npm install..."
cd "$PROJECT_ROOT/frontend"
if [ -f "package.json" ]; then
  npm install --silent
  echo "[Frontend] 의존성 설치 완료 (Node $(node --version))"
else
  echo "[Frontend] package.json 없음 — skip"
fi

# --- .env 확인 ---
cd "$PROJECT_ROOT"
if [ ! -f ".env" ]; then
  if [ -f ".env.example" ]; then
    cp .env.example .env
    echo "[!] .env 파일 생성됨 — R2 키 등 실제 값으로 교체 필요"
  else
    echo "[!] .env.example 없음 — .env 수동 생성 필요"
  fi
fi

# --- Git Hooks ---
cd "$PROJECT_ROOT"
git config core.hooksPath scripts/hooks
echo "[Git] hooks 경로 설정: scripts/hooks"

echo ""
echo "=== 설치 완료 ==="
echo "  개발 서버: bash scripts/dev.sh"
echo "  테스트:    bash scripts/test.sh"
