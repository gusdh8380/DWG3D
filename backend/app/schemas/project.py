from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime


# ─── Upload ───────────────────────────────────────────────────────────────────

class PresignRequest(BaseModel):
    filename: str = Field(..., description="업로드할 파일명 (예: building.dwg)")
    file_size: int = Field(..., gt=0, description="파일 크기 (bytes)")
    content_type: str = Field(default="application/octet-stream")


class PresignResponse(BaseModel):
    project_id: UUID
    upload_url: str
    file_key: str
    expires_in: int = 3600


class UploadCompleteRequest(BaseModel):
    project_id: UUID
    file_key: str


class UploadCompleteResponse(BaseModel):
    project_id: UUID
    job_id: str
    status: str
    message: str


# ─── Project Status ───────────────────────────────────────────────────────────

class StageInfo(BaseModel):
    name: str
    status: str                       # pending | running | done | failed
    duration_sec: Optional[float] = None
    started_at: Optional[datetime] = None


class ProgressInfo(BaseModel):
    stage: str
    percent: int
    message: str


class ProjectStatusResponse(BaseModel):
    project_id: UUID
    name: str
    status: str
    progress: Optional[ProgressInfo] = None
    stages: list[StageInfo] = []
    error_msg: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


# ─── Project List ─────────────────────────────────────────────────────────────

class ProjectSummary(BaseModel):
    project_id: UUID
    name: str
    status: str
    file_type: Optional[str] = None
    object_count: Optional[int] = None
    thumbnail_url: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ─── Manifest ─────────────────────────────────────────────────────────────────

class ManifestResponse(BaseModel):
    """manifest.json 내용을 그대로 반환 (dict)."""
    manifest: dict
