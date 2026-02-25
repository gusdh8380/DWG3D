"""
Upload API
POST /api/v1/upload/presign  — S3 presigned URL 생성
POST /api/v1/upload/complete — 업로드 완료 → 변환 태스크 실행
"""
import logging
import httpx
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.core.storage import get_presigned_upload_url, ensure_bucket
from app.models.project import Project
from app.schemas.project import (
    PresignRequest, PresignResponse,
    UploadCompleteRequest, UploadCompleteResponse,
)

router = APIRouter(prefix="/upload", tags=["upload"])
logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".dwg", ".dxf"}
MAX_SIZE_BYTES = settings.max_upload_size_mb * 1024 * 1024


@router.post("/presign", response_model=PresignResponse)
async def presign_upload(
    body: PresignRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    S3 Presigned Upload URL을 생성하고 프로젝트 레코드를 초기화한다.

    클라이언트는 반환된 upload_url로 직접 PUT 요청하여 파일을 업로드한다.
    """
    # ── 파일명 검증 ────────────────────────────────────────────────────────────
    suffix = Path(body.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"지원하지 않는 파일 형식입니다. 허용: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # ── 크기 검증 ──────────────────────────────────────────────────────────────
    if body.file_size > MAX_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"파일 크기가 최대 {settings.max_upload_size_mb}MB를 초과합니다.",
        )

    # ── 버킷 확인 (개발 환경에서 MinIO 버킷 자동 생성) ──────────────────────
    try:
        ensure_bucket()
    except Exception as e:
        logger.warning(f"버킷 확인 실패 (계속 진행): {e}")

    # ── 프로젝트 레코드 생성 ───────────────────────────────────────────────────
    project_id = uuid4()
    project_name = Path(body.filename).stem
    file_key = f"raw/{project_id}/original{suffix}"

    project = Project(
        id=project_id,
        name=project_name,
        file_key=file_key,
        original_name=body.filename,
        file_size=body.file_size,
        file_type=suffix.lstrip("."),
        status="pending",
    )
    db.add(project)
    await db.commit()

    # ── Presigned URL 생성 ─────────────────────────────────────────────────────
    try:
        upload_url = get_presigned_upload_url(
            key=file_key,
            content_type=body.content_type,
            expires=3600,
        )
    except Exception as e:
        logger.error(f"Presigned URL 생성 실패: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="스토리지 서비스 연결에 실패했습니다.",
        )

    logger.info(f"Presign 생성: project={project_id}, file={body.filename}")

    return PresignResponse(
        project_id=project_id,
        upload_url=upload_url,
        file_key=file_key,
        expires_in=3600,
    )


@router.post("/complete", response_model=UploadCompleteResponse)
async def upload_complete(
    body: UploadCompleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    클라이언트가 S3 업로드를 완료한 후 이 엔드포인트를 호출한다.
    Celery 변환 태스크를 큐에 넣고 즉시 응답한다.
    """
    # ── 프로젝트 조회 ──────────────────────────────────────────────────────────
    project: Project = await db.get(Project, body.project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="프로젝트를 찾을 수 없습니다.",
        )

    if project.status not in ("pending", "failed"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"이미 처리 중인 프로젝트입니다. (status: {project.status})",
        )

    # ── 상태 업데이트 ──────────────────────────────────────────────────────────
    project.status = "uploaded"
    await db.commit()

    # ── Celery 태스크 실행 ─────────────────────────────────────────────────────
    from workers.tasks import convert_file_task
    task = convert_file_task.apply_async(
        args=[str(body.project_id)],
        queue="conversion",
    )

    # ── n8n Webhook 알림 (fire-and-forget) ────────────────────────────────────
    if settings.n8n_webhook_url:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(settings.n8n_webhook_url, json={
                    "project_id": str(body.project_id),
                    "file_key": project.file_key,
                    "file_size": project.file_size,
                    "original_name": project.original_name,
                })
        except Exception as e:
            logger.warning(f"n8n webhook 전송 실패 (무시): {e}")

    logger.info(
        f"변환 태스크 실행: project={body.project_id}, celery_task={task.id}"
    )

    return UploadCompleteResponse(
        project_id=body.project_id,
        job_id=task.id,
        status="processing",
        message="변환이 시작되었습니다. /api/v1/projects/{id}/status 로 진행 상태를 확인하세요.",
    )
