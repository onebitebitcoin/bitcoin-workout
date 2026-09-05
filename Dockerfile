# Stage 1: Build frontend
FROM node:24-alpine AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python backend
FROM python:3.11-slim-bookworm

WORKDIR /app

ARG CACHEBUST=1

# system deps
# libgl1/libglib2.0-0/libgomp1: OpenCV(카툰·발자국 필터) 런타임 요구사항.
# mediapipe 를 지우면서 같이 빼려다 말았다 — 이미지 빌드를 실제로 돌려보지 않고
# 런타임 so 의존성을 줄이면 배포에서만 터진다. 정리하려면 빌드 검증부터.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY VERSION ./
COPY backend/ ./

# Copy built frontend into backend/static
COPY --from=frontend-builder /app/backend/static ./static

ENV ENVIRONMENT=production
ENV PORT=8000

EXPOSE 8000

CMD alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers ${WEB_WORKERS:-2}
