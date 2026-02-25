from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Text, BigInteger, Integer, TIMESTAMP, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from uuid import uuid4, UUID
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.dwg_object import Layer, DwgObject


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[Optional[UUID]] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    file_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    original_name: Mapped[str] = mapped_column(String(500), nullable=False)

    # uploaded | processing | converting | analyzing | complete | failed
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    error_msg: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    file_size: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    file_type: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # dwg or dxf

    glb_key: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    glb_lod1_key: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    glb_lod2_key: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    manifest_key: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    thumbnail_key: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    object_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    jobs: Mapped[list["ConversionJob"]] = relationship(
        "ConversionJob", back_populates="project", cascade="all, delete-orphan"
    )
    layers: Mapped[list["Layer"]] = relationship(
        "Layer", back_populates="project", cascade="all, delete-orphan"
    )
    objects: Mapped[list["DwgObject"]] = relationship(
        "DwgObject", back_populates="project", cascade="all, delete-orphan"
    )


class ConversionJob(Base):
    __tablename__ = "conversion_jobs"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    stage: Mapped[str] = mapped_column(String(100), nullable=False)
    # pending | running | done | failed
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    started_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    log: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="jobs")
