import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from typing import Optional

from app.core.config import settings


def _get_client(endpoint: Optional[str] = None):
    """boto3 S3 클라이언트를 반환한다.

    Args:
        endpoint: None이면 settings.s3_endpoint 사용 (내부 워커용).
                  명시적으로 지정하면 해당 endpoint 사용 (presign URL 생성용).
    """
    ep = endpoint if endpoint is not None else settings.s3_endpoint
    kwargs: dict = {
        "aws_access_key_id": settings.aws_access_key_id,
        "aws_secret_access_key": settings.aws_secret_access_key,
        "region_name": settings.aws_region,
    }
    if ep:
        kwargs["endpoint_url"] = ep
        kwargs["config"] = Config(signature_version="s3v4")
    return boto3.client("s3", **kwargs)


def ensure_bucket() -> None:
    """버킷이 없으면 생성."""
    client = _get_client()
    try:
        client.head_bucket(Bucket=settings.s3_bucket)
    except ClientError:
        client.create_bucket(Bucket=settings.s3_bucket)


def get_presigned_upload_url(
    key: str,
    content_type: str = "application/octet-stream",
    expires: int = 3600,
) -> str:
    """클라이언트가 직접 S3에 PUT할 수 있는 presigned URL을 반환한다.

    로컬 개발 시 S3_PRESIGN_ENDPOINT(=http://localhost:9000)를 사용하여
    signature가 클라이언트에서 접근 가능한 URL로 생성되도록 한다.
    """
    presign_ep = settings.s3_presign_endpoint or settings.s3_endpoint
    client = _get_client(presign_ep)
    return client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.s3_bucket,
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=expires,
    )


def get_presigned_download_url(key: str, expires: int = 3600) -> str:
    client = _get_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": key},
        ExpiresIn=expires,
    )


def upload_bytes(
    key: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> None:
    client = _get_client()
    client.put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
    )


def upload_file(key: str, file_path: str, content_type: str = "application/octet-stream") -> None:
    client = _get_client()
    client.upload_file(file_path, settings.s3_bucket, key, ExtraArgs={"ContentType": content_type})


def download_bytes(key: str) -> bytes:
    client = _get_client()
    response = client.get_object(Bucket=settings.s3_bucket, Key=key)
    return response["Body"].read()


def download_to_file(key: str, dest_path: str) -> None:
    client = _get_client()
    client.download_file(settings.s3_bucket, key, dest_path)


def object_public_url(key: str) -> str:
    """공개 URL 반환 (CDN 또는 MinIO)."""
    if settings.s3_public_url:
        return f"{settings.s3_public_url.rstrip('/')}/{key}"
    if settings.s3_endpoint:
        return f"{settings.s3_endpoint}/{settings.s3_bucket}/{key}"
    return f"https://{settings.s3_bucket}.s3.{settings.aws_region}.amazonaws.com/{key}"
