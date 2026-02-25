#!/bin/sh
set -e

echo "[entrypoint] DB 초기화 중..."
python -m app.db_init

echo "[entrypoint] API 서버 시작..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
