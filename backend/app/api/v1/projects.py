"""
Projects API
GET /api/v1/projects             — 프로젝트 목록
GET /api/v1/projects/{id}/status — 변환 진행 상태
GET /api/v1/projects/{id}/manifest — manifest.json 반환
"""
import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.storage import download_bytes, object_public_url
from app.models.project import Project, ConversionJob
from app.schemas.project import (
    ProjectStatusResponse, ProjectSummary,
    ProgressInfo, StageInfo,
)

router = APIRouter(prefix="/projects", tags=["projects"])
logger = logging.getLogger(__name__)

# 단계별 진행률 매핑
STAGE_PERCENT: dict[str, int] = {
    "pending":   0,
    "uploaded":  5,
    "processing": 10,
    "converting": 30,
    "exporting":  55,
    "analyzing":  70,
    "uploading":  85,
    "complete":  100,
    "failed":    0,
}

STAGE_MESSAGE: dict[str, str] = {
    "pending":   "대기 중...",
    "uploaded":  "파일 업로드 완료. 변환 준비 중...",
    "processing": "파일 분석 중...",
    "converting": "3D 모델 변환 중...",
    "exporting":  "GLB 파일 생성 중...",
    "analyzing":  "구조 분석 중...",
    "uploading":  "결과 저장 중...",
    "complete":  "변환 완료!",
    "failed":    "변환 실패",
}


@router.get("", response_model=list[ProjectSummary])
async def list_projects(
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """프로젝트 목록 (최신순)."""
    result = await db.execute(
        select(Project)
        .order_by(desc(Project.created_at))
        .limit(limit)
        .offset(offset)
    )
    projects = result.scalars().all()

    summaries = []
    for p in projects:
        thumb_url = None
        if p.thumbnail_key:
            thumb_url = object_public_url(p.thumbnail_key)
        summaries.append(
            ProjectSummary(
                project_id=p.id,
                name=p.name,
                status=p.status,
                file_type=p.file_type,
                object_count=p.object_count,
                thumbnail_url=thumb_url,
                created_at=p.created_at,
                completed_at=p.completed_at,
            )
        )
    return summaries


@router.get("/{project_id}/status", response_model=ProjectStatusResponse)
async def get_project_status(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """프로젝트 변환 진행 상태 조회."""
    project: Project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="프로젝트를 찾을 수 없습니다.")

    # 변환 단계 이력 조회
    result = await db.execute(
        select(ConversionJob)
        .where(ConversionJob.project_id == project_id)
        .order_by(ConversionJob.started_at)
    )
    jobs = result.scalars().all()

    stages: list[StageInfo] = [
        StageInfo(
            name=j.stage,
            status=j.status,
            duration_sec=(
                (j.finished_at - j.started_at).total_seconds()
                if j.started_at and j.finished_at else None
            ),
            started_at=j.started_at,
        )
        for j in jobs
    ]

    percent = STAGE_PERCENT.get(project.status, 0)
    message = STAGE_MESSAGE.get(project.status, project.status)
    progress = ProgressInfo(
        stage=project.status,
        percent=percent,
        message=message,
    )

    return ProjectStatusResponse(
        project_id=project.id,
        name=project.name,
        status=project.status,
        progress=progress,
        stages=stages,
        error_msg=project.error_msg,
        created_at=project.created_at,
        completed_at=project.completed_at,
    )


@router.get("/{project_id}/manifest")
async def get_manifest(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """manifest.json 내용을 반환한다."""
    project: Project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="프로젝트를 찾을 수 없습니다.")

    if project.status != "complete":
        raise HTTPException(
            status_code=status.HTTP_425_TOO_EARLY,
            detail=f"아직 변환이 완료되지 않았습니다. (status: {project.status})",
        )

    if not project.manifest_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="manifest.json이 생성되지 않았습니다.",
        )

    try:
        manifest_bytes = download_bytes(project.manifest_key)
        return json.loads(manifest_bytes)
    except Exception as e:
        logger.error(f"manifest 로드 실패: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="manifest.json 로드에 실패했습니다.",
        )
