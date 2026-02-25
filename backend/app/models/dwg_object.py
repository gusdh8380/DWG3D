from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, Boolean, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID as PgUUID, JSONB
from uuid import uuid4, UUID
from typing import Optional, TYPE_CHECKING

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.project import Project


class Layer(Base):
    __tablename__ = "layers"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    color: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)   # "#RRGGBB"
    color_aci: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)   # AutoCAD Color Index
    is_frozen: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_off: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    object_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    project: Mapped["Project"] = relationship("Project", back_populates="layers")
    objects: Mapped[list["DwgObject"]] = relationship(
        "DwgObject", back_populates="layer", cascade="all, delete-orphan"
    )


class DwgObject(Base):
    __tablename__ = "objects"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    layer_id: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("layers.id", ondelete="SET NULL"), nullable=True
    )
    handle: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)    # DWG 핸들 (예: "1A3F")
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)       # MESH, 3DFACE, INSERT 등
    category: Mapped[str] = mapped_column(String(100), nullable=False, default="unknown")
    name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    glb_node_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    bounds: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)        # {"min":[x,y,z],"max":[x,y,z]}
    properties: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)    # 속성 자유 형식

    project: Mapped["Project"] = relationship("Project", back_populates="objects")
    layer: Mapped[Optional["Layer"]] = relationship("Layer", back_populates="objects")

    __table_args__ = (
        Index("idx_objects_project_id", "project_id"),
        Index("idx_objects_category", "category"),
        Index("idx_objects_layer_id", "layer_id"),
    )
