#!/bin/bash
set -e
echo "=== Orange Story Video Worker ==="

# ffmpeg 확인
if ! command -v ffmpeg &> /dev/null; then
    echo "ERROR: ffmpeg not found. Install with: brew install ffmpeg (Mac) or apt install ffmpeg (Ubuntu)"
    exit 1
fi

# Python 의존성
pip install -r requirements.txt --quiet

# 헬스체크
python health_check.py

# 워커 시작
echo "Starting worker..."
python worker.py
