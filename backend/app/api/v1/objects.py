"""
Objects API
GET /api/v1/objects/{id}      — 오브젝트 상세
GET /api/v1/objects           — 프로젝트 내 오브젝트 목록 (필터)
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.dwg_object import DwgObject, Layer
from app.schemas.object import ObjectDetailResponse, LayerSchema, ObjectListResponse

router = APIRouter(prefix="/objects", tags=["objects"])


@router.get("/{object_id}", response_model=ObjectDetailResponse)
async def get_object(
    object_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """오브젝트 상세 정보 (클릭 시 패널 표시용)."""
    result = await db.execute(
        select(DwgObject)
        .where(DwgObject.id == object_id)
        .options(selectinload(DwgObject.layer))
    )
    obj: DwgObject = result.scalar_one_or_none()

    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="오브젝트를 찾을 수 없습니다.")

    layer_schema = None
    if obj.layer:
        layer_schema = LayerSchema(
            id=obj.layer.id,
            name=obj.layer.name,
            color=obj.layer.color,
            category=obj.layer.category,
            is_frozen=obj.layer.is_frozen,
            is_off=obj.layer.is_off,
            object_count=obj.layer.object_count,
        )

    return ObjectDetailResponse(
        id=obj.id,
        handle=obj.handle,
        entity_type=obj.entity_type,
        category=obj.category,
        name=obj.name,
        glb_node_name=obj.glb_node_name,
        layer=layer_schema,
        bounds=obj.bounds,
        properties=obj.properties,
    )


@router.get("", response_model=ObjectListResponse)
async def list_objects(
    project_id: UUID = Query(..., description="프로젝트 ID"),
    category: str | None = Query(None, description="카테고리 필터"),
    layer_id: UUID | None = Query(None, description="레이어 ID 필터"),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """프로젝트 내 오브젝트 목록 (필터링, 페이지네이션)."""
    base_q = select(DwgObject).where(DwgObject.project_id == project_id)
    count_q = select(func.count()).where(DwgObject.project_id == project_id)

    if category:
        base_q = base_q.where(DwgObject.category == category)
        count_q = count_q.where(DwgObject.category == category)
    if layer_id:
        base_q = base_q.where(DwgObject.layer_id == layer_id)
        count_q = count_q.where(DwgObject.layer_id == layer_id)

    total_result = await db.execute(count_q.select_from(DwgObject))
    total = total_result.scalar_one()

    result = await db.execute(
        base_q
        .options(selectinload(DwgObject.layer))
        .limit(limit)
        .offset(offset)
    )
    objects = result.scalars().all()

    items = []
    for obj in objects:
        layer_schema = None
        if obj.layer:
            layer_schema = LayerSchema(
                id=obj.layer.id,
                name=obj.layer.name,
                color=obj.layer.color,
                category=obj.layer.category,
                is_frozen=obj.layer.is_frozen,
                is_off=obj.layer.is_off,
                object_count=obj.layer.object_count,
            )
        items.append(ObjectDetailResponse(
            id=obj.id,
            handle=obj.handle,
            entity_type=obj.entity_type,
            category=obj.category,
            name=obj.name,
            glb_node_name=obj.glb_node_name,
            layer=layer_schema,
            bounds=obj.bounds,
            properties=obj.properties,
        ))

    return ObjectListResponse(items=items, total=total, limit=limit, offset=offset)
