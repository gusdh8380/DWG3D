"""
Mock APS 변환기 — DWG 파일용
APS(Autodesk Platform Services) 없이 절차적으로 3D 씬을 생성한다.
실제 APS 연동 전 파이프라인 전체를 테스트할 수 있다.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import numpy as np

from pipeline.dxf_parser import GeometryData, ParsedLayer, ParsedObject, ParseResult
from pipeline.dxf_parser import (
    _make_node_name, _compute_bounds, _box_from_bounds,
    category_to_rgba, classify_layer,
)

logger = logging.getLogger(__name__)


# ─── 절차적 지오메트리 헬퍼 ──────────────────────────────────────────────────

def _box(x: float, y: float, z: float,
         w: float, d: float, h: float,
         node_name: str, layer: str, handle: str, category: str) -> GeometryData:
    """(x,y,z) 기준점에서 (w,d,h) 크기의 박스."""
    color = category_to_rgba(category)
    return _box_from_bounds(
        [x, y, z], [x + w, y + d, z + h],
        node_name, layer, handle, category, color,
    )


def _cylinder_approx(cx: float, cy: float, z0: float, z1: float,
                     radius: float, segments: int,
                     node_name: str, layer: str, handle: str, category: str) -> GeometryData:
    """원기둥 근사 (세그먼트 수 polygon)."""
    angles = np.linspace(0, 2 * math.pi, segments, endpoint=False)
    xs = cx + radius * np.cos(angles)
    ys = cy + radius * np.sin(angles)

    top_verts = np.column_stack([xs, ys, np.full(segments, z1)])
    bot_verts = np.column_stack([xs, ys, np.full(segments, z0)])
    top_center = np.array([[cx, cy, z1]])
    bot_center = np.array([[cx, cy, z0]])

    verts = np.vstack([bot_verts, top_verts, bot_center, top_center])
    # indices: bot=0..n-1, top=n..2n-1, bot_center=2n, top_center=2n+1
    n = segments
    faces = []
    for i in range(n):
        j = (i + 1) % n
        # side
        faces += [[i, j, n + j], [i, n + j, n + i]]
        # top cap
        faces.append([n + i, n + j, 2 * n + 1])
        # bot cap
        faces.append([j, i, 2 * n])

    color = category_to_rgba(category)
    return GeometryData(
        vertices=verts.astype(np.float64),
        faces=np.array(faces, dtype=np.int32),
        node_name=node_name, layer_name=layer,
        handle=handle, category=category, color_rgba=color,
    )


# ─── 가상 오피스 빌딩 씬 생성 ─────────────────────────────────────────────────

def generate_mock_scene(project_name: str = "MockBuilding") -> ParseResult:
    """
    DWG 변환 없이 절차적으로 오피스 빌딩 씬을 생성한다.
    각 부재는 GLB 노드명을 포함하며, 실제 DWG 파싱 결과와 같은 구조를 반환한다.
    """
    geometries: list[GeometryData] = []
    layer_counts: dict[str, int] = {}

    handle_counter = 0x1A00

    def next_handle() -> str:
        nonlocal handle_counter
        handle_counter += 1
        return format(handle_counter, "X")

    def add_geo(geo: GeometryData, layer: str):
        geometries.append(geo)
        layer_counts[layer] = layer_counts.get(layer, 0) + 1

    # ── 1. 기초 슬래브 ─────────────────────────────────────────────────────────
    h = next_handle()
    add_geo(_box(-25, -15, -0.5, 50, 30, 0.5, f"STRUCTURAL_{h}", "S-SLAB", h, "structural"), "S-SLAB")

    # ── 2. 기둥 (5×3 그리드, 5m 간격) ─────────────────────────────────────────
    for floor in range(3):
        z_base = floor * 4.0
        for col_x in [-20, -10, 0, 10, 20]:
            for col_y in [-10, 0, 10]:
                h = next_handle()
                add_geo(
                    _cylinder_approx(col_x, col_y, z_base, z_base + 4.0,
                                     0.3, 12, f"STRUCTURAL_{h}", "S-COLUMN", h, "structural"),
                    "S-COLUMN",
                )

    # ── 3. 보 (Beam, X/Y 방향) ─────────────────────────────────────────────────
    for floor in range(1, 4):
        z = floor * 4.0 - 0.4
        # X 방향
        for col_y in [-10, 0, 10]:
            for xi in range(4):
                h = next_handle()
                add_geo(
                    _box(-20 + xi * 10, col_y - 0.15, z, 10, 0.3, 0.4,
                         f"STRUCTURAL_{h}", "S-BEAM", h, "structural"),
                    "S-BEAM",
                )
        # Y 방향
        for col_x in [-20, -10, 0, 10, 20]:
            h = next_handle()
            add_geo(
                _box(col_x - 0.15, -10, z, 0.3, 20, 0.4,
                     f"STRUCTURAL_{h}", "S-BEAM", h, "structural"),
                "S-BEAM",
            )

    # ── 4. 슬래브 (층별) ──────────────────────────────────────────────────────
    for floor in range(1, 4):
        z = floor * 4.0 - 0.3
        h = next_handle()
        add_geo(
            _box(-25, -15, z, 50, 30, 0.3, f"STRUCTURAL_{h}", "S-SLAB", h, "structural"),
            "S-SLAB",
        )

    # ── 5. 외벽 (건축) ────────────────────────────────────────────────────────
    wall_defs = [
        (-25, -15, 25, 0.3, 12),   # 남측
        (-25,  14.7, 25, 0.3, 12), # 북측
        (-25, -15, 0.3, 30, 12),   # 서측
        ( 24.7, -15, 0.3, 30, 12), # 동측
    ]
    for wx, wy, ww, wd, wh in wall_defs:
        h = next_handle()
        add_geo(
            _box(wx, wy, 0, ww, wd, wh, f"ARCHITECTURAL_{h}", "A-WALL", h, "architectural"),
            "A-WALL",
        )

    # ── 6. HVAC 덕트 (기계) ───────────────────────────────────────────────────
    for floor in range(3):
        z = floor * 4.0 + 3.3
        for duct_y in [-5, 5]:
            h = next_handle()
            add_geo(
                _box(-22, duct_y - 0.15, z, 44, 0.3, 0.3,
                     f"MECHANICAL_{h}", "M-HVAC", h, "mechanical"),
                "M-HVAC",
            )
        # 주 덕트 Y방향
        h = next_handle()
        add_geo(
            _box(-0.25, -12, z, 0.5, 24, 0.5, f"MECHANICAL_{h}", "M-HVAC", h, "mechanical"),
            "M-HVAC",
        )

    # ── 7. 배수 파이프 (배관) ─────────────────────────────────────────────────
    for i, px in enumerate([-15, 0, 15]):
        h = next_handle()
        add_geo(
            _cylinder_approx(px, -13, -0.5, 12.5, 0.1, 8,
                             f"PLUMBING_{h}", "P-DRAIN", h, "plumbing"),
            "P-DRAIN",
        )

    # ── 8. 전기 배선 트레이 (전기) ───────────────────────────────────────────
    for floor in range(3):
        z = floor * 4.0 + 3.6
        h = next_handle()
        add_geo(
            _box(-23, -13, z, 46, 0.2, 0.1, f"ELECTRICAL_{h}", "E-TRAY", h, "electrical"),
            "E-TRAY",
        )

    # ── 레이어 정의 ────────────────────────────────────────────────────────────
    layer_defs = [
        ("S-SLAB",    "#8C8C8C", 8,  "structural"),
        ("S-COLUMN",  "#8C8C8C", 8,  "structural"),
        ("S-BEAM",    "#8C8C8C", 8,  "structural"),
        ("A-WALL",    "#E6C9A0", 30, "architectural"),
        ("M-HVAC",    "#3399FF", 5,  "mechanical"),
        ("P-DRAIN",   "#00CC66", 3,  "plumbing"),
        ("E-TRAY",    "#FFCC00", 2,  "electrical"),
    ]
    from uuid import uuid4
    parsed_layers = [
        ParsedLayer(
            id=str(uuid4()),
            name=name, color_hex=color, color_aci=aci,
            is_frozen=False, is_off=False,
            category=cat,
            object_count=layer_counts.get(name, 0),
        )
        for name, color, aci, cat in layer_defs
    ]
    layer_by_name = {pl.name: pl for pl in parsed_layers}

    # ── ParsedObject 생성 ──────────────────────────────────────────────────────
    parsed_objects: list[ParsedObject] = []
    for geo in geometries:
        bounds = _compute_bounds(geo.vertices)
        pl = layer_by_name.get(geo.layer_name)
        parsed_objects.append(ParsedObject(
            id=str(uuid4()),
            layer_name=geo.layer_name,
            handle=geo.handle,
            entity_type="MOCK_SOLID",
            category=geo.category,
            name=geo.node_name,
            glb_node_name=geo.node_name,
            bounds=bounds,
            properties={"mock": True, "project": project_name},
        ))

    # ── 전체 Bounds ────────────────────────────────────────────────────────────
    all_verts = np.vstack([g.vertices for g in geometries])
    scene_bounds = _compute_bounds(all_verts)

    logger.info(
        f"Mock 씬 생성 완료: geometries={len(geometries)}, "
        f"objects={len(parsed_objects)}, layers={len(parsed_layers)}"
    )

    return ParseResult(
        layers=parsed_layers,
        objects=parsed_objects,
        geometries=geometries,
        bounds=scene_bounds,
        stats={
            "total_entities": len(geometries),
            "geometry_count": len(geometries),
            "layer_count": len(parsed_layers),
            "is_mock": True,
        },
    )
