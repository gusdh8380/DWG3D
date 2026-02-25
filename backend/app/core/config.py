from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ─── Database ──────────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://dwg3d:secret@db:5432/dwg3d"
    database_sync_url: str = "postgresql+psycopg2://dwg3d:secret@db:5432/dwg3d"

    # ─── Redis / Celery ────────────────────────────────────────────────────────
    redis_url: str = "redis://redis:6379/0"

    # ─── Storage ───────────────────────────────────────────────────────────────
    s3_endpoint: Optional[str] = None           # 내부 S3 접근 (워커용): http://minio:9000
    s3_presign_endpoint: Optional[str] = None   # 클라이언트 presign URL 생성용: http://localhost:9000
    s3_bucket: str = "dwg3d"
    aws_access_key_id: str = "minioadmin"
    aws_secret_access_key: str = "minioadmin"
    aws_region: str = "us-east-1"
    s3_public_url: Optional[str] = None         # CDN or MinIO public base URL

    # ─── APS (Autodesk Platform Services) ──────────────────────────────────────
    use_mock_conversion: bool = True
    aps_client_id: Optional[str] = None
    aps_client_secret: Optional[str] = None

    # ─── n8n ───────────────────────────────────────────────────────────────────
    n8n_webhook_url: Optional[str] = None

    # ─── App ───────────────────────────────────────────────────────────────────
    debug: bool = True
    max_upload_size_mb: int = 500
    temp_dir: str = "/tmp/dwg3d"


settings = Settings()
