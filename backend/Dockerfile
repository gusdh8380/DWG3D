FROM python:3.12-slim

WORKDIR /app

# 시스템 의존성 (psycopg2, trimesh 등)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성 먼저 설치 (레이어 캐싱 활용)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사
COPY . .

# 파이프라인 임시 디렉토리
RUN mkdir -p /tmp/dwg3d

# 엔트리포인트 실행 권한
RUN chmod +x entrypoint.sh

EXPOSE 8000

CMD ["/app/entrypoint.sh"]
