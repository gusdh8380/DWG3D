"""
테스트용 3D DXF 파일 생성기
ezdxf로 다양한 3D 엔티티를 포함한 DXF를 생성한다.
파이프라인 end-to-end 테스트에 사용한다.

실행:
    pip install ezdxf
    python tests/create_test_dxf.py
    → tests/sample_3d.dxf 생성
"""
import math
import sys
from pathlib import Path

try:
    import ezdxf
    from ezdxf.math import Vec3
except ImportError:
    print("ERROR: ezdxf가 설치되지 않았습니다. pip install ezdxf")
    sys.exit(1)

OUTPUT = Path(__file__).parent / "sample_3d.dxf"


def add_box_as_3dfaces(msp, x, y, z, w, d, h, layer: str):
    """박스를 3DFACE 삼각형으로 추가한다."""
    pts = [
        Vec3(x, y, z), Vec3(x+w, y, z), Vec3(x+w, y+d, z), Vec3(x, y+d, z),
        Vec3(x, y, z+h), Vec3(x+w, y, z+h), Vec3(x+w, y+d, z+h), Vec3(x, y+d, z+h),
    ]
    # Bottom face (2 triangles)
    msp.add_3dface([pts[0], pts[1], pts[2], pts[3]], dxfattribs={"layer": layer})
    # Top face
    msp.add_3dface([pts[4], pts[5], pts[6], pts[7]], dxfattribs={"layer": layer})
    # Side faces
    sides = [(0,1,5,4), (1,2,6,5), (2,3,7,6), (3,0,4,7)]
    for a, b, c, d_idx in sides:
        msp.add_3dface([pts[a], pts[b], pts[c], pts[d_idx]], dxfattribs={"layer": layer})


def add_mesh_cylinder(msp, cx, cy, z0, z1, radius, segments, layer: str):
    """원기둥을 MESH 엔티티로 추가한다."""
    mesh = msp.add_mesh(dxfattribs={"layer": layer})
    angles = [2 * math.pi * i / segments for i in range(segments)]

    with mesh.edit_data() as mesh_data:
        vertices = []
        # Bottom ring
        for a in angles:
            vertices.append(Vec3(cx + radius * math.cos(a), cy + radius * math.sin(a), z0))
        # Top ring
        for a in angles:
            vertices.append(Vec3(cx + radius * math.cos(a), cy + radius * math.sin(a), z1))
        # Centers
        vertices.append(Vec3(cx, cy, z0))   # index: 2*segments
        vertices.append(Vec3(cx, cy, z1))   # index: 2*segments+1

        mesh_data.vertices = vertices
        n = segments
        faces = []
        for i in range(n):
            j = (i + 1) % n
            # Side quad → 2 triangles
            faces.append([i, j, n + j, n + i])
            # Bottom cap
            faces.append([j, i, 2 * n])
            # Top cap
            faces.append([n + i, n + j, 2 * n + 1])
        mesh_data.faces = faces


def main():
    doc = ezdxf.new("R2010")
    doc.units = 6  # Meters

    # ── 레이어 정의 ──────────────────────────────────────────────────────────
    layers = [
        ("S-BEAM",    1),   # 빨강
        ("S-COLUMN",  2),   # 노랑
        ("S-SLAB",    8),   # 회색
        ("M-HVAC",    5),   # 파랑
        ("A-WALL",    30),  # 갈색
        ("E-TRAY",    3),   # 초록
        ("P-DRAIN",   4),   # 시안
    ]
    for name, color in layers:
        layer = doc.layers.add(name)
        layer.color = color

    msp = doc.modelspace()

    # ── 기초 슬래브 (3DFACE) ─────────────────────────────────────────────────
    add_box_as_3dfaces(msp, -20, -12, -0.5, 40, 24, 0.5, "S-SLAB")

    # ── 기둥 (MESH 원기둥) ───────────────────────────────────────────────────
    for col_x in [-15, -5, 5, 15]:
        for col_y in [-8, 0, 8]:
            add_mesh_cylinder(msp, col_x, col_y, 0, 3.5, 0.25, 12, "S-COLUMN")

    # ── 보 (3DFACE 박스) ─────────────────────────────────────────────────────
    for col_y in [-8, 0, 8]:
        for xi in range(3):
            add_box_as_3dfaces(
                msp, -15 + xi * 10, col_y - 0.15, 3.1,
                10, 0.3, 0.4, "S-BEAM"
            )
    # Y방향 보
    for col_x in [-15, -5, 5, 15]:
        add_box_as_3dfaces(msp, col_x - 0.15, -8, 3.1, 0.3, 16, 0.4, "S-BEAM")

    # ── 층 슬래브 ─────────────────────────────────────────────────────────────
    add_box_as_3dfaces(msp, -20, -12, 3.5, 40, 24, 0.2, "S-SLAB")

    # ── 외벽 (3DFACE) ─────────────────────────────────────────────────────────
    # 남측
    add_box_as_3dfaces(msp, -20, -12, 0, 40, 0.2, 3.5, "A-WALL")
    # 북측
    add_box_as_3dfaces(msp, -20,  11.8, 0, 40, 0.2, 3.5, "A-WALL")
    # 서측
    add_box_as_3dfaces(msp, -20, -12, 0, 0.2, 24, 3.5, "A-WALL")
    # 동측
    add_box_as_3dfaces(msp, 19.8, -12, 0, 0.2, 24, 3.5, "A-WALL")

    # ── HVAC 덕트 (MESH 박스) ────────────────────────────────────────────────
    for duct_y in [-4, 4]:
        add_mesh_cylinder(msp, 0, duct_y, 3.2, 3.2, 0.01, 4, "M-HVAC")  # degenerate → skip
    add_box_as_3dfaces(msp, -18, -0.2, 3.15, 36, 0.4, 0.35, "M-HVAC")
    add_box_as_3dfaces(msp, -18, -4.2, 3.15, 36, 0.4, 0.35, "M-HVAC")

    # ── 전기 트레이 ───────────────────────────────────────────────────────────
    add_box_as_3dfaces(msp, -19, -11, 3.4, 38, 0.2, 0.1, "E-TRAY")

    # ── 배수 파이프 (MESH 원기둥) ─────────────────────────────────────────────
    for px in [-10, 0, 10]:
        add_mesh_cylinder(msp, px, -11, -0.5, 3.7, 0.08, 8, "P-DRAIN")

    # ── 저장 ──────────────────────────────────────────────────────────────────
    doc.saveas(str(OUTPUT))
    print(f"테스트 DXF 생성 완료: {OUTPUT}")
    print(f"포함된 레이어: {[l[0] for l in layers]}")


if __name__ == "__main__":
    main()
