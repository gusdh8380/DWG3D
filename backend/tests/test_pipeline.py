"""
파이프라인 통합 테스트
DXF 파일 → 파싱 → GLB 변환 → manifest.json 생성까지 검증한다.

실행:
    python -m pytest tests/test_pipeline.py -v
    또는
    python tests/test_pipeline.py
"""
import json
import os
import sys
from pathlib import Path

# PYTHONPATH 설정 (backend/ 루트에서 실행)
sys.path.insert(0, str(Path(__file__).parent.parent))

TEST_DXF = Path(__file__).parent / "sample_3d.dxf"


def test_mock_pipeline():
    """Mock 파이프라인 (DWG 없이 절차적 씬)."""
    from pipeline.mock_aps import generate_mock_scene
    from pipeline.glb_exporter import export_glb
    from pipeline.manifest_builder import build_manifest, build_objects_index

    print("\n[1] Mock 씬 생성 중...")
    result = generate_mock_scene("TestBuilding")
    assert len(result.geometries) > 0, "지오메트리가 생성되어야 함"
    assert len(result.layers) > 0,     "레이어가 있어야 함"
    assert len(result.objects) > 0,    "오브젝트가 있어야 함"
    print(f"    geometries={len(result.geometries)}, layers={len(result.layers)}, objects={len(result.objects)}")

    print("[2] GLB 익스포트 중...")
    glb_result = export_glb(result.geometries)
    assert len(glb_result.lod0) > 0, "LOD0 GLB가 비어있으면 안 됨"
    assert len(glb_result.lod1) > 0, "LOD1 GLB가 비어있으면 안 됨"
    assert len(glb_result.lod2) > 0, "LOD2 GLB가 비어있으면 안 됨"
    print(f"    lod0={len(glb_result.lod0)//1024}KB, lod1={len(glb_result.lod1)//1024}KB, lod2={len(glb_result.lod2)//1024}KB")

    print("[3] Manifest 생성 중...")
    manifest = build_manifest(
        project_id="test-project-id",
        project_name="TestBuilding",
        source_filename="test.dwg",
        parse_result=result,
        asset_urls={
            "lod0": "http://localhost:9000/dwg3d/glb/test/model_lod0.glb",
            "lod1": "http://localhost:9000/dwg3d/glb/test/model_lod1.glb",
            "lod2": "http://localhost:9000/dwg3d/glb/test/model_lod2.glb",
            "objects_index": "http://localhost:9000/dwg3d/json/test/objects_index.json",
        },
    )
    assert manifest["version"] == "1.0"
    assert len(manifest["layers"]) > 0
    assert len(manifest["categories"]) > 0
    assert len(manifest["objects"]) > 0
    print(f"    layers={len(manifest['layers'])}, categories={len(manifest['categories'])}, objects={len(manifest['objects'])}")

    obj_index = build_objects_index(result)
    assert "by_node_name" in obj_index["index"]
    print(f"    objects_index: {len(obj_index['index']['by_node_name'])} entries")

    # GLB 파일 저장 (확인용)
    out_dir = Path(__file__).parent / "output"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "mock_lod0.glb").write_bytes(glb_result.lod0)
    (out_dir / "mock_lod2.glb").write_bytes(glb_result.lod2)
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2)
    )
    print(f"    결과 파일 저장: {out_dir}/")

    print("\n✅ Mock 파이프라인 테스트 통과!")
    return True


def test_dxf_pipeline():
    """DXF 실제 파싱 파이프라인."""
    if not TEST_DXF.exists():
        print(f"\n[SKIP] 테스트 DXF 없음. 먼저 실행: python tests/create_test_dxf.py")
        return True

    from pipeline.dxf_parser import parse_dxf
    from pipeline.glb_exporter import export_glb
    from pipeline.manifest_builder import build_manifest

    print(f"\n[1] DXF 파싱 중: {TEST_DXF}")
    result = parse_dxf(str(TEST_DXF))
    print(f"    geometries={len(result.geometries)}, layers={len(result.layers)}, objects={len(result.objects)}")
    print(f"    bounds={result.bounds}")
    print(f"    stats={result.stats}")

    if len(result.geometries) == 0:
        print("    ⚠️  3D 지오메트리가 없습니다. DXF에 3D 엔티티가 포함되어야 합니다.")
        return True

    print("[2] GLB 익스포트 중...")
    glb_result = export_glb(result.geometries)
    print(f"    lod0={len(glb_result.lod0)//1024}KB, faces={glb_result.total_faces}")

    out_dir = Path(__file__).parent / "output"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "dxf_lod0.glb").write_bytes(glb_result.lod0)
    print(f"    GLB 저장: {out_dir}/dxf_lod0.glb")

    print("\n✅ DXF 파이프라인 테스트 통과!")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("DWG3D 파이프라인 테스트")
    print("=" * 60)
    ok1 = test_mock_pipeline()
    ok2 = test_dxf_pipeline()
    sys.exit(0 if (ok1 and ok2) else 1)
