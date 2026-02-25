from pydantic import BaseModel
from typing import Optional, Any
from uuid import UUID


class BoundsSchema(BaseModel):
    min: list[float]   # [x, y, z]
    max: list[float]   # [x, y, z]


class LayerSchema(BaseModel):
    id: UUID
    name: str
    color: Optional[str] = None
    category: Optional[str] = None
    is_frozen: bool = False
    is_off: bool = False
    object_count: int = 0

    model_config = {"from_attributes": True}


class ObjectDetailResponse(BaseModel):
    id: UUID
    handle: Optional[str] = None
    entity_type: str
    category: str
    name: Optional[str] = None
    glb_node_name: Optional[str] = None
    layer: Optional[LayerSchema] = None
    bounds: Optional[dict[str, Any]] = None
    properties: Optional[dict[str, Any]] = None

    model_config = {"from_attributes": True}


class ObjectListResponse(BaseModel):
    items: list[ObjectDetailResponse]
    total: int
    limit: int
    offset: int
