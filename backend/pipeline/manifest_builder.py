"""
Manifest Builder
ParseResult + 에셋 URL → manifest.json dict 조립
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from pipeline.dxf_parser import ParseResult, ParsedLayer, ParsedObject

logger = logging.getLogger(__name__)


def _category_color(category: str) -> str:
    palette = {
        "structural":    "#8C8C8C",
        "mechanical":    "#3399FF",
        "electrical":    "#FFCC00",
        "plumbing":      "#00CC66",
        "architectural": "#E6C9A0",
        "civil":         "#99CC66",
        "furniture":     "#CC9966",
        "annotation":    "#888888",
        "unknown":       "#AAAAAA",
    }
    return palette.get(category, "#AAAAAA")


def _build_categories(layers: list[ParsedLayer], objects: list[ParsedObject]) -> list[dict]:
    """레이어/오브젝트 목록에서 카테고리 집계를 생성한다."""
    category_data: dict[str, dict] = {}

    for layer in layers:
        cat = layer.category or "unknown"
        if cat not in category_data:
            category_data[cat] = {
                "id": cat,
                "label": _category_label(cat),
                "color": _category_color(cat),
                "object_count": 0,
                "layer_ids": [],
                "visible": True,
            }
        category_data[cat]["object_count"] += layer.object_count
        category_data[cat]["layer_ids"].append(layer.id)

    return list(category_data.values())


def _category_label(category: str) -> str:
    labels = {
        "structural":    "구조",
        "mechanical":    "기계",
        "electrical":    "전기",
        "plumbing":      "배관",
        "architectural": "건축",
        "civil":         "토목",
        "furniture":     "가구/장비",
        "annotation":    "주석",
        "unknown":       "미분류",
    }
    return labels.get(category, category)


def build_manifest(
    project_id: str | UUID,
    project_name: str,
    source_filename: str,
    parse_result: ParseResult,
    asset_urls: dict,   # {"lod0": url, "lod1": url, "lod2": url, "thumbnail": url}
    scale_factor: float = 1.0,
) -> dict:
    """
    manifest.json 딕셔너리를 조립한다.

    Args:
        project_id:      프로젝트 UUID
        project_name:    프로젝트 이름
        source_filename: 원본 파일명
        parse_result:    DXF/Mock 파서 결과
        asset_urls:      S3/CDN URL 맵
        scale_factor:    좌표 정규화 스케일 (mm→m 이면 0.001)

    Returns:
        manifest dict (JSON 직렬화 가능)
    """
    pr = parse_result

    # 레이어 ID 맵 (이름 → id)
    layer_id_map = {pl.name: pl.id for pl in pr.layers}

    manifest = {
        "version": "1.0",
        "project_id": str(project_id),
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),

        "metadata": {
            "source_file": source_filename,
            "project_name": project_name,
            "scale_factor": scale_factor,
            "bounds": pr.bounds,
            "stats": {
                "total_objects":    len(pr.objects),
                "total_layers":     len(pr.layers),
                "total_categories": len(set(pl.category for pl in pr.layers)),
                **pr.stats,
            },
        },

        "assets": {
            "glb": {
                "lod0": asset_urls.get("lod0", ""),
                "lod1": asset_urls.get("lod1", ""),
                "lod2": asset_urls.get("lod2", ""),
            },
            "thumbnail": asset_urls.get("thumbnail", ""),
            "objects_index": asset_urls.get("objects_index", ""),
        },

        "layers": [
            {
                "id":           pl.id,
                "name":         pl.name,
                "color":        pl.color_hex,
                "color_aci":    pl.color_aci,
                "is_frozen":    pl.is_frozen,
                "is_off":       pl.is_off,
                "category":     pl.category,
                "object_count": pl.object_count,
            }
            for pl in pr.layers
        ],

        "categories": _build_categories(pr.layers, pr.objects),

        "objects": [
            {
                "id":            obj.id,
                "handle":        obj.handle,
                "entity_type":   obj.entity_type,
                "category":      obj.category,
                "layer_id":      layer_id_map.get(obj.layer_name),
                "name":          obj.name,
                "glb_node_name": obj.glb_node_name,
                "bounds":        obj.bounds,
                "properties":    obj.properties,
            }
            for obj in pr.objects
        ],
    }

    return manifest


def build_objects_index(parse_result: ParseResult) -> dict:
    """
    Unity에서 빠른 노드→오브젝트 조회를 위한 경량 인덱스.
    """
    by_node: dict[str, str] = {}
    by_handle: dict[str, str] = {}

    for obj in parse_result.objects:
        if obj.glb_node_name:
            by_node[obj.glb_node_name] = obj.id
        if obj.handle:
            by_handle[obj.handle] = obj.id

    return {
        "version": "1.0",
        "index": {
            "by_node_name": by_node,
            "by_handle":    by_handle,
        },
    }
