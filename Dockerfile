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
# libgl1/libglib2.0-0/libgomp1: mediapipe(운동열 필터) manylinux wheel 런타임 요구사항
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# opencv-contrib-python(GUI 포함) 충돌 방지 — backend/requirements.txt 주석 참고
RUN pip install --no-cache-dir --no-deps mediapipe==0.10.35

COPY VERSION ./
COPY backend/ ./

# Copy built frontend into backend/static
COPY --from=frontend-builder /app/backend/static ./static

ENV ENVIRONMENT=production
ENV PORT=8000

EXPOSE 8000

CMD alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers ${WEB_WORKERS:-2}
