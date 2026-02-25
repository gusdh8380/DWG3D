"""
GLB 익스포터 — trimesh 기반
GeometryData 목록을 받아 GLB 바이트를 생성한다.
LOD0(원본), LOD1(50%), LOD2(20%) 세 가지 레벨을 생성한다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

try:
    import trimesh
    from trimesh import Trimesh, Scene
    from trimesh.visual import ColorVisuals
except ImportError:
    trimesh = None  # type: ignore

from pipeline.dxf_parser import GeometryData

logger = logging.getLogger(__name__)


@dataclass
class GlbExportResult:
    lod0: bytes   # 풀 디테일
    lod1: bytes   # 50% 감소
    lod2: bytes   # 80% 감소 (초기 표시용)
    node_count: int
    total_faces: int


# ─── 유틸리티 ─────────────────────────────────────────────────────────────────

def _geo_to_trimesh(geo: GeometryData) -> Optional[Trimesh]:
    """GeometryData → trimesh.Trimesh."""
    if trimesh is None:
        raise ImportError("trimesh 패키지가 설치되지 않았습니다")
    if len(geo.vertices) == 0 or len(geo.faces) == 0:
        return None
    try:
        mesh = Trimesh(
            vertices=geo.vertices,
            faces=geo.faces,
            process=True,   # 중복 제거, 법선 계산
        )
        # 면이 0개 남으면 건너뜀
        if len(mesh.faces) == 0:
            return None

        # Vertex color 적용 (RGBA 0~1 → 0~255)
        r, g, b, a = geo.color_rgba
        color_arr = np.tile(
            [int(r * 255), int(g * 255), int(b * 255), int(a * 255)],
            (len(mesh.vertices), 1),
        ).astype(np.uint8)
        mesh.visual = ColorVisuals(mesh=mesh, vertex_colors=color_arr)
        return mesh
    except Exception as e:
        logger.debug(f"Trimesh 변환 오류 ({geo.node_name}): {e}")
        return None


def _decimate(mesh: Trimesh, ratio: float) -> Trimesh:
    """면 수를 ratio 비율로 감소."""
    target = max(4, int(len(mesh.faces) * ratio))
    if len(mesh.faces) <= target:
        return mesh
    try:
        return mesh.simplify_quadric_decimation(target)
    except Exception:
        return mesh  # 실패 시 원본 반환


def _build_scene(geometries: list[GeometryData]) -> tuple[Scene, dict[str, Trimesh]]:
    """GeometryData 목록 → trimesh.Scene."""
    scene = Scene()
    mesh_map: dict[str, Trimesh] = {}

    for geo in geometries:
        mesh = _geo_to_trimesh(geo)
        if mesh is None:
            continue
        scene.add_geometry(mesh, geom_name=geo.node_name)
        mesh_map[geo.node_name] = mesh

    return scene, mesh_map


def _scene_to_glb(scene: Scene) -> bytes:
    """trimesh Scene → GLB bytes."""
    if len(scene.geometry) == 0:
        # 빈 씬 → 빈 큐브 하나 추가 (Unity가 빈 GLB 처리 실패 방지)
        placeholder = Trimesh(
            vertices=[[0,0,0],[1,0,0],[0,1,0],[0,0,1]],
            faces=[[0,1,2],[0,1,3],[0,2,3],[1,2,3]],
            process=False,
        )
        scene.add_geometry(placeholder, geom_name="PLACEHOLDER")

    return scene.export(file_type="glb")


# ─── 메인 익스포터 ────────────────────────────────────────────────────────────

def export_glb(geometries: list[GeometryData]) -> GlbExportResult:
    """
    GeometryData 목록을 GLB 세 가지 LOD로 변환한다.

    Args:
        geometries: dxf_parser.parse_dxf() 또는 mock_aps에서 반환된 목록

    Returns:
        GlbExportResult (lod0, lod1, lod2 bytes)
    """
    if trimesh is None:
        raise ImportError("trimesh 패키지가 설치되지 않았습니다")

    logger.info(f"GLB 익스포트 시작: geometry count={len(geometries)}")

    # ── LOD0 씬 빌드 ──────────────────────────────────────────────────────────
    lod0_scene, mesh_map = _build_scene(geometries)
    lod0_bytes = _scene_to_glb(lod0_scene)

    total_faces = sum(len(m.faces) for m in mesh_map.values())
    node_count = len(mesh_map)

    logger.info(f"LOD0: nodes={node_count}, faces={total_faces}, size={len(lod0_bytes)//1024}KB")

    # ── LOD1 (50%) ────────────────────────────────────────────────────────────
    lod1_scene = Scene()
    for name, mesh in mesh_map.items():
        lod1_mesh = _decimate(mesh, 0.5)
        lod1_scene.add_geometry(lod1_mesh, geom_name=name)
    lod1_bytes = _scene_to_glb(lod1_scene)
    logger.info(f"LOD1: size={len(lod1_bytes)//1024}KB")

    # ── LOD2 (20%) ────────────────────────────────────────────────────────────
    lod2_scene = Scene()
    for name, mesh in mesh_map.items():
        lod2_mesh = _decimate(mesh, 0.2)
        lod2_scene.add_geometry(lod2_mesh, geom_name=name)
    lod2_bytes = _scene_to_glb(lod2_scene)
    logger.info(f"LOD2: size={len(lod2_bytes)//1024}KB")

    return GlbExportResult(
        lod0=lod0_bytes,
        lod1=lod1_bytes,
        lod2=lod2_bytes,
        node_count=node_count,
        total_faces=total_faces,
    )
