"""
DXF 파서 — ezdxf 기반
DXF 파일에서 레이어, 객체, 3D 지오메트리를 추출한다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional
from uuid import uuid4

import numpy as np

try:
    import ezdxf
    from ezdxf.math import Vec3, Matrix44
except ImportError:
    ezdxf = None  # type: ignore

logger = logging.getLogger(__name__)

# ─── 카테고리 분류 규칙 ──────────────────────────────────────────────────────
CATEGORY_RULES: dict[str, list[str]] = {
    "structural":    ["S-", "STRUCT", "BEAM", "COLUMN", "SLAB", "WALL-STR", "FOOTING"],
    "mechanical":    ["M-", "MECH", "HVAC", "PIPE", "DUCT", "EQUIP"],
    "electrical":    ["E-", "ELEC", "POWER", "LIGHT", "CABLE", "CONDUIT"],
    "plumbing":      ["P-", "PLUMB", "DRAIN", "WATER", "SANIT"],
    "architectural": ["A-", "ARCH", "ROOM", "DOOR", "WINDOW", "CEIL", "FLOOR", "WALL"],
    "civil":         ["C-", "CIVIL", "TOPO", "ROAD", "GRADE"],
    "furniture":     ["FF&E", "FURN", "EQUIP-FF"],
    "annotation":    ["ANNO", "DIM", "TEXT", "HATCH", "NOTE"],
}

ACI_TO_HEX: dict[int, str] = {
    1: "#FF0000", 2: "#FFFF00", 3: "#00FF00", 4: "#00FFFF",
    5: "#0000FF", 6: "#FF00FF", 7: "#FFFFFF", 8: "#808080",
    9: "#C0C0C0", 256: "#FFFFFF",  # 256 = BYLAYER default
}


# ─── 데이터 클래스 ────────────────────────────────────────────────────────────

@dataclass
class GeometryData:
    vertices: np.ndarray   # shape (N, 3)  float64
    faces: np.ndarray      # shape (M, 3)  int32  (삼각형)
    node_name: str         # GLB 노드명 예: "S_BEAM_1A3F"
    layer_name: str
    handle: str
    category: str
    color_rgba: tuple[float, float, float, float] = (0.7, 0.7, 0.7, 1.0)


@dataclass
class ParsedLayer:
    id: str
    name: str
    color_hex: str
    color_aci: int
    is_frozen: bool
    is_off: bool
    category: str
    object_count: int = 0


@dataclass
class ParsedObject:
    id: str
    layer_name: str
    handle: str
    entity_type: str
    category: str
    name: Optional[str]
    glb_node_name: str
    bounds: dict         # {"min": [x,y,z], "max": [x,y,z]}
    properties: dict


@dataclass
class ParseResult:
    layers: list[ParsedLayer] = field(default_factory=list)
    objects: list[ParsedObject] = field(default_factory=list)
    geometries: list[GeometryData] = field(default_factory=list)
    bounds: dict = field(default_factory=dict)
    stats: dict = field(default_factory=dict)


# ─── 유틸리티 ─────────────────────────────────────────────────────────────────

def classify_layer(layer_name: str) -> str:
    upper = layer_name.upper()
    for category, keywords in CATEGORY_RULES.items():
        if any(upper.startswith(kw.upper()) or kw.upper() in upper for kw in keywords):
            return category
    return "unknown"


def aci_to_hex(aci: int) -> str:
    return ACI_TO_HEX.get(aci, "#AAAAAA")


def category_to_rgba(category: str) -> tuple[float, float, float, float]:
    palette = {
        "structural":    (0.70, 0.70, 0.70, 1.0),
        "mechanical":    (0.20, 0.60, 1.00, 1.0),
        "electrical":    (1.00, 0.90, 0.00, 1.0),
        "plumbing":      (0.00, 0.80, 0.40, 1.0),
        "architectural": (0.90, 0.80, 0.70, 1.0),
        "civil":         (0.60, 0.80, 0.40, 1.0),
        "furniture":     (0.80, 0.60, 0.40, 1.0),
        "annotation":    (0.50, 0.50, 0.50, 1.0),
        "unknown":       (0.60, 0.60, 0.60, 1.0),
    }
    return palette.get(category, (0.6, 0.6, 0.6, 1.0))


def _safe_handle(entity) -> str:
    try:
        return entity.dxf.handle or str(uuid4())[:8].upper()
    except Exception:
        return str(uuid4())[:8].upper()


def _compute_bounds(verts: np.ndarray) -> dict:
    if len(verts) == 0:
        return {"min": [0, 0, 0], "max": [0, 0, 0]}
    return {
        "min": verts.min(axis=0).tolist(),
        "max": verts.max(axis=0).tolist(),
    }


def _make_node_name(category: str, handle: str) -> str:
    cat_clean = category.upper().replace("-", "_")
    return f"{cat_clean}_{handle}"


# ─── 엔티티 → GeometryData 변환 ──────────────────────────────────────────────

def _extract_mesh_entity(entity, category: str, color: tuple) -> Optional[GeometryData]:
    """MESH 엔티티 → GeometryData."""
    try:
        b = entity.get_data()  # MeshData
        verts = np.array([[v.x, v.y, v.z] for v in b.vertices], dtype=np.float64)
        # ezdxf faces는 정수 리스트 (n-gon)
        triangles = []
        for face in b.faces:
            if len(face) == 3:
                triangles.append(face[:3])
            elif len(face) == 4:
                triangles.append([face[0], face[1], face[2]])
                triangles.append([face[0], face[2], face[3]])
        if not triangles or len(verts) == 0:
            return None
        faces = np.array(triangles, dtype=np.int32)
        handle = _safe_handle(entity)
        return GeometryData(
            vertices=verts, faces=faces,
            node_name=_make_node_name(category, handle),
            layer_name=entity.dxf.layer,
            handle=handle, category=category, color_rgba=color,
        )
    except Exception as e:
        logger.debug(f"MESH extract failed: {e}")
        return None


def _extract_3dface_entity(entity, category: str, color: tuple) -> Optional[GeometryData]:
    """3DFACE 엔티티 → 삼각형/쿼드 GeometryData."""
    try:
        pts = [
            entity.dxf.vtx0, entity.dxf.vtx1,
            entity.dxf.vtx2, entity.dxf.vtx3,
        ]
        verts = np.array([[p.x, p.y, p.z] for p in pts], dtype=np.float64)
        v0, v1, v2, v3 = verts[0], verts[1], verts[2], verts[3]
        if np.allclose(v2, v3):
            faces = np.array([[0, 1, 2]], dtype=np.int32)
        else:
            faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
        handle = _safe_handle(entity)
        return GeometryData(
            vertices=verts, faces=faces,
            node_name=_make_node_name(category, handle),
            layer_name=entity.dxf.layer,
            handle=handle, category=category, color_rgba=color,
        )
    except Exception as e:
        logger.debug(f"3DFACE extract failed: {e}")
        return None


def _box_from_bounds(min_pt: list, max_pt: list, node_name: str,
                     layer: str, handle: str, category: str,
                     color: tuple) -> GeometryData:
    """경계 박스를 삼각형 메시로 생성 (ACIS 폴백용)."""
    x0, y0, z0 = min_pt
    x1, y1, z1 = max_pt
    verts = np.array([
        [x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
        [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1],
    ], dtype=np.float64)
    faces = np.array([
        [0,1,2],[0,2,3],  # bottom
        [4,6,5],[4,7,6],  # top
        [0,4,5],[0,5,1],  # front
        [2,6,7],[2,7,3],  # back
        [0,3,7],[0,7,4],  # left
        [1,5,6],[1,6,2],  # right
    ], dtype=np.int32)
    return GeometryData(
        vertices=verts, faces=faces,
        node_name=node_name, layer_name=layer,
        handle=handle, category=category, color_rgba=color,
    )


def _extract_solid3d_entity(entity, category: str, color: tuple) -> Optional[GeometryData]:
    """3DSOLID(ACIS) → bounding box 폴백."""
    try:
        bbox = entity.bbox()
        if bbox is None:
            return None
        mn = [bbox.extmin.x, bbox.extmin.y, bbox.extmin.z]
        mx = [bbox.extmax.x, bbox.extmax.y, bbox.extmax.z]
        handle = _safe_handle(entity)
        return _box_from_bounds(
            mn, mx, _make_node_name(category, handle),
            entity.dxf.layer, handle, category, color,
        )
    except Exception as e:
        logger.debug(f"3DSOLID extract failed: {e}")
        return None


def _extract_polyface_mesh(entity, category: str, color: tuple) -> Optional[GeometryData]:
    """POLYFACE MESH 엔티티 → GeometryData."""
    try:
        verts_raw = []
        faces_raw = []
        for v in entity.vertices:
            verts_raw.append([v.dxf.location.x, v.dxf.location.y, v.dxf.location.z])
        # Polyface face vertex indices (1-based in DXF, negative = invisible edge)
        for v in entity.vertices:
            if v.is_face_record:
                idxs = [
                    abs(v.dxf.vtx0) - 1, abs(v.dxf.vtx1) - 1,
                    abs(v.dxf.vtx2) - 1, abs(v.dxf.vtx3) - 1,
                ]
                if idxs[2] == idxs[3]:
                    faces_raw.append(idxs[:3])
                else:
                    faces_raw.append(idxs[:3])
                    faces_raw.append([idxs[0], idxs[2], idxs[3]])

        if not verts_raw or not faces_raw:
            return None
        verts = np.array(verts_raw, dtype=np.float64)
        faces = np.array(faces_raw, dtype=np.int32)
        handle = _safe_handle(entity)
        return GeometryData(
            vertices=verts, faces=faces,
            node_name=_make_node_name(category, handle),
            layer_name=entity.dxf.layer,
            handle=handle, category=category, color_rgba=color,
        )
    except Exception as e:
        logger.debug(f"POLYFACE MESH extract failed: {e}")
        return None


def _extract_entity(entity, layer_map: dict[str, ParsedLayer]) -> Optional[GeometryData]:
    """엔티티 타입별로 GeometryData를 반환. 지원하지 않으면 None."""
    layer_name = getattr(entity.dxf, "layer", "0")
    parsed_layer = layer_map.get(layer_name)
    category = parsed_layer.category if parsed_layer else classify_layer(layer_name)
    color = category_to_rgba(category)
    dxf_type = entity.dxftype()

    if dxf_type == "MESH":
        return _extract_mesh_entity(entity, category, color)
    elif dxf_type == "3DFACE":
        return _extract_3dface_entity(entity, category, color)
    elif dxf_type == "3DSOLID":
        return _extract_solid3d_entity(entity, category, color)
    elif dxf_type == "POLYLINE" and entity.is_poly_face_mesh:
        return _extract_polyface_mesh(entity, category, color)
    # LINE, ARC, CIRCLE 등은 3D geometry에서 제외 (2D 도면 요소)
    return None


# ─── 메인 파서 ───────────────────────────────────────────────────────────────

def parse_dxf(file_path: str) -> ParseResult:
    """
    DXF 파일을 파싱하여 ParseResult를 반환한다.

    Args:
        file_path: DXF 파일 경로

    Returns:
        ParseResult (layers, objects, geometries, bounds, stats)
    """
    if ezdxf is None:
        raise ImportError("ezdxf 패키지가 설치되지 않았습니다: pip install ezdxf")

    logger.info(f"DXF 파싱 시작: {file_path}")
    doc = ezdxf.readfile(file_path)
    msp = doc.modelspace()

    # ── 레이어 파싱 ────────────────────────────────────────────────────────────
    parsed_layers: list[ParsedLayer] = []
    layer_map: dict[str, ParsedLayer] = {}

    for layer in doc.layers:
        try:
            name = layer.dxf.name
            aci = layer.dxf.color if layer.dxf.hasattr("color") else 7
            color_hex = aci_to_hex(abs(aci))
            is_frozen = layer.is_frozen()
            is_off = aci < 0  # ACI 음수 = OFF

            pl = ParsedLayer(
                id=str(uuid4()),
                name=name,
                color_hex=color_hex,
                color_aci=abs(aci),
                is_frozen=is_frozen,
                is_off=is_off,
                category=classify_layer(name),
            )
            parsed_layers.append(pl)
            layer_map[name] = pl
        except Exception as e:
            logger.debug(f"레이어 파싱 오류 {layer}: {e}")

    # layer "0" 기본 보장
    if "0" not in layer_map:
        pl0 = ParsedLayer(
            id=str(uuid4()), name="0", color_hex="#FFFFFF",
            color_aci=7, is_frozen=False, is_off=False, category="unknown",
        )
        parsed_layers.insert(0, pl0)
        layer_map["0"] = pl0

    # ── 엔티티 파싱 ────────────────────────────────────────────────────────────
    geometries: list[GeometryData] = []
    parsed_objects: list[ParsedObject] = []
    all_vertices: list[np.ndarray] = []

    entity_count = 0
    geo_count = 0

    for entity in msp:
        entity_count += 1
        try:
            geo = _extract_entity(entity, layer_map)
            if geo is not None and len(geo.vertices) > 0:
                geometries.append(geo)
                all_vertices.append(geo.vertices)
                geo_count += 1

                # 카운터 증가
                if geo.layer_name in layer_map:
                    layer_map[geo.layer_name].object_count += 1

                # ParsedObject 생성
                bounds = _compute_bounds(geo.vertices)
                layer_n = geo.layer_name
                props = {}
                # ATTRIB/XDATA 수집 (가능한 경우)
                try:
                    for attrib in entity.attribs if hasattr(entity, "attribs") else []:
                        props[attrib.dxf.tag] = attrib.dxf.text
                except Exception:
                    pass

                parsed_objects.append(ParsedObject(
                    id=str(uuid4()),
                    layer_name=layer_n,
                    handle=geo.handle,
                    entity_type=entity.dxftype(),
                    category=geo.category,
                    name=None,
                    glb_node_name=geo.node_name,
                    bounds=bounds,
                    properties=props,
                ))
        except Exception as e:
            logger.debug(f"엔티티 처리 오류: {e}")

    # ── 전체 Bounds 계산 ────────────────────────────────────────────────────────
    if all_vertices:
        all_pts = np.vstack(all_vertices)
        scene_bounds = _compute_bounds(all_pts)
    else:
        scene_bounds = {"min": [0, 0, 0], "max": [0, 0, 0]}

    logger.info(
        f"DXF 파싱 완료: entities={entity_count}, 3D geometries={geo_count}, "
        f"layers={len(parsed_layers)}"
    )

    return ParseResult(
        layers=parsed_layers,
        objects=parsed_objects,
        geometries=geometries,
        bounds=scene_bounds,
        stats={
            "total_entities": entity_count,
            "geometry_count": geo_count,
            "layer_count": len(parsed_layers),
        },
    )
