# DWG3D — 전체 시스템 아키텍처 설계서

> 버전: 1.0 | 작성일: 2026-02-24
> 역할: CAD/BIM 파이프라인 × Unity WebGL × SaaS 백엔드 × n8n 오케스트레이션

---

## 목차

1. [전체 시스템 다이어그램](#1-전체-시스템-다이어그램)
2. [레이어별 상세 설계](#2-레이어별-상세-설계)
3. [DWG → GLB 변환 파이프라인](#3-dwg--glb-변환-파이프라인)
4. [n8n 오케스트레이션 아키텍처](#4-n8n-오케스트레이션-아키텍처)
5. [구조 JSON 설계](#5-구조-json-설계)
6. [주요 API 설계](#6-주요-api-설계)
7. [Unity WebGL 로딩 흐름](#7-unity-webgl-로딩-흐름)
8. [WebGL 최적화 전략](#8-webgl-최적화-전략)
9. [기술 스택 확정](#9-기술-스택-확정)
10. [기술 리스크 분석](#10-기술-리스크-분석)
11. [4주 MVP 개발 로드맵](#11-4주-mvp-개발-로드맵)

---

## 1. 전체 시스템 다이어그램

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            BROWSER (Client)                                  │
│                                                                               │
│   ┌──────────────────────────┐        ┌──────────────────────────────────┐   │
│   │    Next.js Frontend      │        │      Unity WebGL (iframe)        │   │
│   │  ─────────────────────   │        │  ────────────────────────────    │   │
│   │  · 파일 업로드 UI        │        │  · GLB 렌더링                    │   │
│   │  · 진행상태 폴링         │        │  · Orbit 카메라                  │   │
│   │  · 레이어/카테고리 패널  │◄──JS──►│  · 객체 클릭 하이라이트          │   │
│   │  · 상세정보 사이드패널   │ Bridge │  · 카테고리 필터                 │   │
│   │  · 프로젝트 목록         │        │  · 레이어 숨김/표시              │   │
│   └──────────┬───────────────┘        └──────────────────────────────────┘   │
└──────────────┼──────────────────────────────────────────────────────────────┘
               │ HTTPS
               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         API Gateway (Nginx / Caddy)                          │
│                    Rate Limiting · SSL Termination · Routing                 │
└────────┬──────────────────────────────────────┬────────────────────────────┘
         │                                      │
         ▼                                      ▼
┌────────────────────┐              ┌───────────────────────┐
│   Main API Server  │              │   n8n Orchestrator    │
│   (FastAPI/Python) │              │   (Self-hosted)       │
│ ─────────────────  │              │ ─────────────────     │
│ · POST /upload     │──Webhook────►│ · Upload Trigger      │
│ · GET  /status     │              │ · Conversion Workflow │
│ · GET  /project    │◄─Callback───│ · Retry Logic         │
│ · GET  /manifest   │              │ · Slack 알림          │
│ · WS   /events     │              │ · 썸네일 생성 트리거  │
└────────┬───────────┘              └──────────┬────────────┘
         │                                     │
         ▼                                     ▼
┌────────────────────────────────────────────────────────────┐
│                    Job Queue (Redis + Celery)               │
│              conversion_queue · analysis_queue             │
└─────────────────────────┬──────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐
│  Conversion  │  │  Semantic    │  │  Thumbnail           │
│  Worker      │  │  Analysis    │  │  Generator           │
│ ──────────── │  │  Worker      │  │ ──────────────────   │
│ DWG→OBJ(APS) │  │ ──────────── │  │ Blender headless     │
│ OBJ→GLB      │  │ 엔티티 분류  │  │ 256×256 PNG 생성     │
│ 좌표 정규화  │  │ 계층 구조화  │  │ S3 업로드            │
│ 메시 최적화  │  │ JSON 생성    │  └──────────────────────┘
│ LOD 생성     │  │ DB 저장      │
└──────┬───────┘  └──────┬───────┘
       │                 │
       └────────┬────────┘
                ▼
┌───────────────────────────────────────────────────────────┐
│                      Storage Layer                         │
│                                                           │
│  ┌──────────────────┐    ┌──────────────────────────┐    │
│  │   AWS S3 Buckets  │    │   PostgreSQL + pgvector  │    │
│  │ ─────────────── │    │ ──────────────────────── │    │
│  │ /raw/   .dwg     │    │ projects                 │    │
│  │ /glb/   .glb     │    │ job_status               │    │
│  │ /json/  manifest │    │ objects (JSONB)           │    │
│  │ /thumb/ .png     │    │ layers                   │    │
│  │ /lod/   lod0-3   │    │ embeddings (AI확장용)    │    │
│  └──────────────────┘    └──────────────────────────┘    │
│                                                           │
│  ┌──────────────────┐    ┌──────────────────────────┐    │
│  │      Redis        │    │   CDN (CloudFront)       │    │
│  │ ─────────────── │    │ ──────────────────────── │    │
│  │ job:status       │    │ GLB / JSON 캐싱          │    │
│  │ session cache    │    │ Unity WebGL Build 배포   │    │
│  │ rate limit       │    │ 썸네일 서빙              │    │
│  └──────────────────┘    └──────────────────────────┘    │
└───────────────────────────────────────────────────────────┘
```

---

## 2. 레이어별 상세 설계

### 2-1. Upload Layer

**역할**: 파일 수신, 유효성 검증, S3 저장, n8n 트리거

```
Browser
  │
  ├─ Step 1: POST /api/upload/presign  → { upload_url, project_id, file_key }
  │          (S3 Presigned URL 요청)
  │
  ├─ Step 2: PUT {upload_url}          → S3 직접 업로드 (백엔드 우회)
  │          Content-Type: application/octet-stream
  │          X-Amz-Meta-Project-Id: {project_id}
  │
  └─ Step 3: POST /api/upload/complete → { job_id }
             { project_id, file_key, file_size, checksum }
             → S3 Event → n8n Webhook 트리거
```

**파일 검증 규칙**:
- 확장자: `.dwg`, `.dxf` 만 허용
- 크기 상한: 500MB (MVP), 2GB (확장)
- Magic bytes 검증: DWG = `AC10xx`, `AC1027` 등
- 바이러스 스캔: ClamAV (선택)

**DB 레코드 생성**:
```sql
INSERT INTO projects (id, user_id, file_key, original_name, status, created_at)
VALUES ($1, $2, $3, $4, 'uploaded', NOW());
```

---

### 2-2. Conversion Layer

**역할**: DWG → GLB 변환, 좌표 정규화, 메시 최적화

**변환 전략: APS (Autodesk Platform Services) + 로컬 후처리 하이브리드**

```
[이유] DWG 3D 객체(3DSolid, Body, ACIS)는 독점 포맷이므로
       ODA SDK 또는 APS 없이는 완전한 지오메트리 추출 불가능.
       APS Model Derivative API는 가장 신뢰성 높은 옵션.
```

단계별 처리:
```
Raw DWG (S3)
    │
    ▼ [Step 1] APS Upload & Job Submit
Autodesk Platform Services
    · POST /oss/v2/buckets/{bucket}/objects → DWG 업로드
    · POST /modelderivative/v2/designdata/job
      { input: { urn: "..." },
        output: { formats: [{ type: "obj", advanced: { unit: "meter" } }] } }
    │
    ▼ [Step 2] Poll until manifest.status == "success"
    · GET /modelderivative/v2/designdata/{urn}/manifest
    │
    ▼ [Step 3] Download OBJ + MTL
OBJ + MTL Files (temp storage)
    │
    ▼ [Step 4] Python 후처리 (custom worker)
    · trimesh 로딩: trimesh.load("model.obj")
    · 좌표 정규화: APS unit=meter 파라미터로 처리, 검증
    · 메시 통합: merge_by_material()
    · 디시메이션: Quadric Edge Collapse (목표 면수: 원본의 30%)
    · UV 생성: trimesh.unwrap_uv() (텍스처 없는 경우)
    │
    ▼ [Step 5] GLB Export
    · pygltflib 또는 trimesh.export("model.glb")
    · GLB 내부 구조: Mesh per Category (카테고리별 분리)
    │
    ▼ [Step 6] LOD 생성
    · LOD0: 원본 기준 면수 (근거리)
    · LOD1: 50% 감소 (중거리)
    · LOD2: 80% 감소 (원거리)
    · 각 LOD → 별도 GLB 파일
    │
    ▼ [Step 7] S3 업로드
    /glb/{project_id}/model_lod0.glb
    /glb/{project_id}/model_lod1.glb
    /glb/{project_id}/model_lod2.glb
```

---

### 2-3. Semantic Analysis Layer

**역할**: 엔티티 구조 분석, 카테고리 분류, manifest JSON 생성

**ODA File Converter (무료) 또는 ezdxf로 보조 파싱**:
```
DWG → (ODA File Converter CLI) → DXF
DXF → (ezdxf Python) → Entity Objects
    │
    ├─ LAYER 엔티티 → layers[] 구성
    ├─ BLOCK 정의 → blocks{} 구성
    ├─ INSERT 엔티티 → objects[] 배치 정보
    ├─ 3DSOLID / BODY / REGION → 3D 객체 마킹
    ├─ ATTDEF / ATTRIB → 속성 데이터
    └─ XDATA / Extension Dict → 커스텀 메타데이터
```

**카테고리 자동 분류 규칙**:
```python
CATEGORY_RULES = {
    "structural": ["S-", "STRUCT", "BEAM", "COLUMN", "WALL"],
    "mechanical": ["M-", "MECH", "HVAC", "PIPE", "DUCT"],
    "electrical": ["E-", "ELEC", "POWER", "LIGHT"],
    "plumbing":   ["P-", "PLUMB", "DRAIN", "WATER"],
    "architectural": ["A-", "ARCH", "ROOM", "DOOR", "WINDOW"],
    "civil":      ["C-", "CIVIL", "TOPO", "ROAD"],
    "furniture":  ["FF&E", "FURN", "EQUIP"],
    "annotation": ["ANNO", "DIM", "TEXT", "HATCH"],
}
# 레이어명 prefix 매칭 + XDATA 속성 기반 분류
```

---

### 2-4. Storage Layer

**S3 버킷 구조**:
```
dwg3d-storage/
├── raw/
│   └── {project_id}/original.dwg
├── intermediate/
│   └── {project_id}/model.obj
├── glb/
│   └── {project_id}/
│       ├── model_lod0.glb      (< 50MB 목표)
│       ├── model_lod1.glb      (< 15MB 목표)
│       ├── model_lod2.glb      (< 5MB 목표)
│       └── chunks/             (분할 로딩용)
│           ├── structural.glb
│           ├── mechanical.glb
│           └── architectural.glb
├── json/
│   └── {project_id}/
│       ├── manifest.json       (전체 구조)
│       └── objects_index.json  (객체 인덱스, 빠른 조회)
└── thumbnails/
    └── {project_id}/thumb_256.png
```

**PostgreSQL 스키마**:
```sql
-- 프로젝트
CREATE TABLE projects (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL,
    name        TEXT NOT NULL,
    file_key    TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'uploaded',
    -- uploaded | processing | converting | analyzing | complete | failed
    error_msg   TEXT,
    file_size   BIGINT,
    glb_size    BIGINT,
    object_count INT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- 레이어
CREATE TABLE layers (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id  UUID REFERENCES projects(id),
    name        TEXT NOT NULL,
    color       TEXT,          -- "#FF5733"
    is_frozen   BOOLEAN DEFAULT FALSE,
    is_off      BOOLEAN DEFAULT FALSE,
    linetype    TEXT,
    lineweight  REAL,
    object_count INT DEFAULT 0
);

-- 오브젝트 (대용량 → JSONB + GIN 인덱스)
CREATE TABLE objects (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id   UUID REFERENCES projects(id),
    layer_id     UUID REFERENCES layers(id),
    handle       TEXT NOT NULL,    -- DWG 고유 핸들 (예: "1A3F")
    entity_type  TEXT NOT NULL,    -- "3DSOLID", "INSERT", "MESH" 등
    category     TEXT NOT NULL,    -- "structural", "mechanical" 등
    name         TEXT,
    glb_mesh_id  TEXT,             -- GLB 내 mesh name (Unity 매핑용)
    bounds       JSONB,            -- {"min":[x,y,z],"max":[x,y,z]}
    properties   JSONB,            -- 모든 속성 (ATTRIB, XDATA 포함)
    created_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_objects_project  ON objects(project_id);
CREATE INDEX idx_objects_category ON objects(category);
CREATE INDEX idx_objects_props    ON objects USING GIN (properties);

-- 변환 작업 이력
CREATE TABLE conversion_jobs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id  UUID REFERENCES projects(id),
    stage       TEXT NOT NULL,     -- "aps_upload","aps_convert","glb_export",...
    status      TEXT NOT NULL,     -- "pending","running","done","failed"
    started_at  TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    attempt     INT DEFAULT 1,
    log         TEXT,
    metadata    JSONB
);
```

---

### 2-5. Unity WebGL Layer

**역할**: 3D 렌더링, 인터랙션, JS Bridge 통신

**Unity 프로젝트 핵심 구성**:
```
Unity WebGL Project/
├── Assets/
│   ├── Scripts/
│   │   ├── Core/
│   │   │   ├── AppController.cs      # 초기화, 상태 관리
│   │   │   ├── ModelLoader.cs        # GLB 로딩 (GLTFast)
│   │   │   └── ManifestLoader.cs     # JSON 파싱
│   │   ├── Camera/
│   │   │   └── OrbitCamera.cs        # Orbit 컨트롤
│   │   ├── Interaction/
│   │   │   ├── ObjectPicker.cs       # Raycast 클릭
│   │   │   └── HighlightController.cs # 하이라이트 셰이더
│   │   ├── Filter/
│   │   │   ├── LayerFilter.cs        # 레이어 토글
│   │   │   └── CategoryFilter.cs     # 카테고리 토글
│   │   ├── Bridge/
│   │   │   ├── JSBridge.cs           # JS↔Unity 통신
│   │   │   └── BridgeMessages.cs     # 메시지 타입 정의
│   │   └── LOD/
│   │       └── LODSwitcher.cs        # 카메라 거리 기반 LOD
│   ├── Plugins/
│   │   └── WebGL/
│   │       └── bridge.jslib          # JS Plugin
│   └── StreamingAssets/             # 런타임 로딩 에셋
```

---

## 3. DWG → GLB 변환 파이프라인

### 단계별 상세 처리

```
[STAGE 0] Pre-validation (< 5초)
  Input:  raw .dwg file (S3)
  Actions:
    · DWG 버전 확인 (AC1015=2000, AC1024=2010, AC1032=2018)
    · 파일 무결성 검사 (체크섬 검증)
    · 3D 엔티티 존재 여부 사전 체크 (ezdxf로 DXF 변환 후 확인)
    · 예상 변환 시간/크기 추정 → 사용자 UI 표시
  Output: validation_result { valid, dwg_version, has_3d, estimated_objects }

[STAGE 1] APS Upload (파일 크기에 따라 10초~5분)
  Input:  .dwg S3 URL
  Actions:
    · APS 인증 토큰 획득 (Client Credentials OAuth2)
    · S3 → APS OSS 버킷 스트리밍 업로드
      POST /oss/v2/buckets/dwg3d-aps/objects/{file_key}
      (100MB 이상 → Resumable Upload, Chunk 크기 5MB)
    · URN 생성 (base64 encoded)
  Output: aps_urn, aps_object_id

[STAGE 2] APS Model Derivative (2분~30분)
  Input:  aps_urn
  Actions:
    · 변환 Job 제출
      POST /modelderivative/v2/designdata/job
      {
        "input": { "urn": "{aps_urn}" },
        "output": {
          "formats": [{
            "type": "obj",
            "advanced": {
              "exportFileStructure": "single",
              "unit": "meter",
              "modelGuid": "...",
              "objectIds": [-1]    // -1 = 전체
            }
          }]
        }
      }
    · 상태 폴링 (10초 간격, 최대 60분)
      GET /modelderivative/v2/designdata/{urn}/manifest
    · 완료 시 OBJ + MTL 다운로드
      GET /modelderivative/v2/designdata/{urn}/manifest
         → derivative.urn → 다운로드 URL
  Output: model.obj, model.mtl (S3 intermediate/)

[STAGE 3] Geometric Post-processing (1분~10분)
  Input:  model.obj
  Library: trimesh, numpy, scipy
  Actions:
    (a) 로딩 및 씬 분해
        scene = trimesh.load("model.obj", force="scene")
        meshes = {name: geom for name, geom in scene.geometry.items()}

    (b) 좌표계 검증 및 정규화
        # APS 변환 시 unit=meter 지정했으나 실제 확인 필요
        bounds = scene.bounds  # [[xmin,ymin,zmin],[xmax,ymax,zmax]]
        scale = detect_unit_scale(bounds)  # mm면 0.001, cm이면 0.01
        if scale != 1.0:
            scene.apply_scale(scale)
        # Y-up → Z-up은 Unity에서 처리 (GLB는 Y-up 표준)

    (c) 메시 통합 (카테고리별)
        # 같은 카테고리 메시는 단일 mesh로 병합 → draw call 감소
        category_meshes = group_by_category(meshes, layer_category_map)
        merged = {cat: trimesh.util.concatenate(ms)
                  for cat, ms in category_meshes.items()}

    (d) 메시 최적화
        for cat, mesh in merged.items():
            # 중복 버텍스 제거
            mesh.merge_vertices()
            # 디제너레이트 삼각형 제거
            mask = mesh.nondegenerate_faces()
            mesh.update_faces(mask)
            # Quadric Decimation (목표: 원본의 30%)
            target_faces = max(100, int(len(mesh.faces) * 0.3))
            if len(mesh.faces) > target_faces:
                decimated = mesh.simplify_quadric_decimation(target_faces)
                merged[cat] = decimated

    (e) 개별 객체 Mesh 분리 (클릭 인터랙션용)
        # 통합 mesh에서 원래 분리된 submesh 정보를 metadata로 보존
        for obj_handle, submesh in per_object_meshes.items():
            submesh.metadata["handle"] = obj_handle

  Output: optimized scene (in memory)

[STAGE 4] GLB 생성 (30초~3분)
  Input:  optimized scene
  Actions:
    (a) 씬 구조 설정
        # GLB node 이름 = mesh 식별자 (Unity에서 이름으로 조회)
        # 구조: root → category_group → object_mesh
        #   root
        #   ├── Structural
        #   │   ├── BEAM_001   (name = DWG handle "1A3F")
        #   │   └── COLUMN_002
        #   ├── Mechanical
        #   │   └── PIPE_001
        #   └── ...

    (b) 머티리얼 설정
        # 레이어 색상 → PBR 머티리얼 (metallic=0, roughness=0.8)
        # 기본 색상 팔레트로 카테고리별 색상 지정
        materials = {
          "structural":    (0.7, 0.7, 0.7, 1.0),  # 회색
          "mechanical":    (0.2, 0.6, 1.0, 1.0),  # 파랑
          "electrical":    (1.0, 0.9, 0.0, 1.0),  # 노랑
          "architectural": (0.9, 0.8, 0.7, 1.0),  # 베이지
          "plumbing":      (0.0, 0.8, 0.4, 1.0),  # 초록
        }

    (c) Draco 압축 적용
        # pip install draco
        scene.export("model_lod0.glb",
                     include_normals=True,
                     compression="draco")

    (d) LOD 변형 생성
        LOD0 = model (최적화 후 기준)
        LOD1 = simplify_quadric_decimation(LOD0, 0.5)  → model_lod1.glb
        LOD2 = simplify_quadric_decimation(LOD0, 0.2)  → model_lod2.glb

    (e) 카테고리별 청크 GLB (분할 로딩용)
        for category in categories:
            export_chunk(category_meshes[category],
                         f"chunks/{category}.glb")

  Output: model_lod0/1/2.glb, chunks/*.glb → S3 /glb/{project_id}/

[STAGE 5] Manifest JSON 생성
  Input:  DXF parsed data + GLB node map
  → 섹션 5 참고

[STAGE 6] 썸네일 생성 (Blender headless)
  blender --background --python render_thumb.py -- model_lod2.glb output.png
  · 카메라: isometric 45° 뷰
  · 해상도: 512×512
  · 배경: 투명 (PNG)
  Output: thumb_256.png → S3 /thumbnails/{project_id}/
```

---

## 4. n8n 오케스트레이션 아키텍처

### n8n을 사용할 경우 전체 흐름 변화

**기존 구조 (n8n 없음)**:
```
API Server → Celery Queue → Worker (단일 Python 프로세스 내 오케스트레이션)
```

**n8n 도입 후 구조**:
```
API Server → S3 Event → n8n Webhook → n8n Workflow → Worker HTTP API
                                     ↑                ↓
                                  Retry Logic      Callback
                                  Slack 알림
                                  DB 상태 업데이트
```

### n8n 워크플로우 설계

#### Workflow 1: DWG Upload Trigger

```
[Webhook: POST /n8n/upload-complete]
  ├─ Trigger: API Server가 S3 업로드 완료 후 호출
  │   Body: { project_id, file_key, file_size, user_id }
  │
  ▼
[Set Node: 초기 변수]
  · project_id, file_key, attempt = 1
  │
  ▼
[HTTP Request: DB Status Update]
  · PATCH /api/internal/projects/{project_id}/status
  · Body: { status: "processing" }
  │
  ▼
[HTTP Request: Conversion Worker 실행]
  · POST http://conversion-worker:8001/convert
  · Body: { project_id, file_key }
  · Timeout: 3600s
  │
  ├─ [Success] → Workflow 2로 전달
  └─ [Error]   → Workflow: Error Handler
```

#### Workflow 2: 변환 완료 후처리

```
[Webhook: POST /n8n/conversion-complete]
  ├─ Trigger: Conversion Worker 완료 콜백
  │   Body: { project_id, glb_keys, object_count, duration_sec }
  │
  ▼
[Parallel Execution] ─────────────────────────────────────────
  │                                                           │
  ▼                                                           ▼
[HTTP Request: Semantic Analysis]              [HTTP Request: Thumbnail Gen]
  · POST /api/internal/analyze                   · POST /api/internal/thumbnail
  · Body: { project_id }                         · Body: { project_id }
  │                                               │
  ▼                                               ▼
[HTTP Request: DB Update]                     [HTTP Request: DB Update]
  · objects 저장                                · thumbnail_key 저장
  │                                               │
  └──────────────────────┬────────────────────────┘
                         ▼
              [HTTP Request: Status = "complete"]
                         │
                         ▼
              [Slack: 완료 알림]
                · "✅ {project_name} 변환 완료"
                · "객체 수: {object_count}, 소요: {duration}초"
                · "🔗 {viewer_url}"
                         │
                         ▼
              [HTTP Request: WebSocket 이벤트 발행]
                · POST /api/internal/events/publish
                · Body: { type: "conversion_complete", project_id }
```

#### Workflow 3: 실패 재시도

```
[Error Handler Workflow]
  Input: { project_id, stage, error, attempt }
  │
  ▼
[IF: attempt <= 3]
  ├─ True:
  │   ▼
  │  [Wait: exponential backoff]
  │   · attempt=1: 30초
  │   · attempt=2: 5분
  │   · attempt=3: 30분
  │   ▼
  │  [HTTP: 재시도 요청]
  │   · stage에 따라 해당 Worker 재호출
  │   · attempt + 1
  │
  └─ False (3회 초과):
      ▼
     [HTTP: Status = "failed"]
      ▼
     [Slack: 실패 알림 (#alerts 채널)]
      · "❌ {project_id} 변환 실패"
      · "Stage: {stage}, Error: {error}"
      · "수동 개입 필요"
      ▼
     [Email: 사용자 실패 알림]
```

#### n8n 도입 시 아키텍처 차이점

| 항목 | n8n 없음 | n8n 도입 |
|------|---------|---------|
| 재시도 로직 | Worker 코드 내 구현 | n8n 워크플로우에서 선언적 관리 |
| 알림 | Worker에서 직접 Slack API | n8n Slack Node |
| 모니터링 | 로그 분석 필요 | n8n UI에서 실행 이력 시각적 확인 |
| 단계 추가 | 코드 변경 + 배포 | n8n 워크플로우 수정만 |
| 병렬 실행 | asyncio/threading 구현 | n8n Parallel Node |
| 개발 복잡도 | 낮음 (단일 코드베이스) | 초기 높음 (n8n 학습) |
| 운영 복잡도 | 높음 (오류 추적 어려움) | 낮음 (UI로 모니터링) |

**결론**: MVP에서는 n8n 도입. Worker들은 각각 독립 HTTP API로 설계하고, n8n은 오케스트레이션만 담당.

---

## 5. 구조 JSON 설계

### manifest.json (전체 구조)

```json
{
  "version": "1.0",
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "generated_at": "2026-02-24T12:00:00Z",

  "metadata": {
    "source_file": "office_building.dwg",
    "dwg_version": "AC1032",
    "unit_source": "mm",
    "unit_display": "m",
    "scale_factor": 0.001,
    "coordinate_system": "WCS",
    "bounds": {
      "min": { "x": -50.5, "y": -30.2, "z": 0.0 },
      "max": { "x": 50.5,  "y": 30.2,  "z": 45.6 },
      "center": { "x": 0.0, "y": 0.0, "z": 22.8 }
    },
    "stats": {
      "total_objects":    1842,
      "total_layers":     47,
      "total_categories": 6,
      "glb_lod0_size_kb": 38400,
      "glb_lod1_size_kb": 12800,
      "glb_lod2_size_kb": 4200
    }
  },

  "assets": {
    "glb": {
      "lod0": "https://cdn.dwg3d.io/glb/550e.../model_lod0.glb",
      "lod1": "https://cdn.dwg3d.io/glb/550e.../model_lod1.glb",
      "lod2": "https://cdn.dwg3d.io/glb/550e.../model_lod2.glb"
    },
    "chunks": {
      "structural":    "https://cdn.dwg3d.io/glb/550e.../chunks/structural.glb",
      "mechanical":    "https://cdn.dwg3d.io/glb/550e.../chunks/mechanical.glb",
      "electrical":    "https://cdn.dwg3d.io/glb/550e.../chunks/electrical.glb",
      "architectural": "https://cdn.dwg3d.io/glb/550e.../chunks/architectural.glb",
      "plumbing":      "https://cdn.dwg3d.io/glb/550e.../chunks/plumbing.glb"
    },
    "objects_index": "https://cdn.dwg3d.io/json/550e.../objects_index.json",
    "thumbnail":     "https://cdn.dwg3d.io/thumbnails/550e.../thumb_256.png"
  },

  "layers": [
    {
      "id": "layer-001",
      "name": "S-BEAM",
      "color": "#8C8C8C",
      "color_aci": 8,
      "linetype": "Continuous",
      "lineweight": 0.25,
      "is_frozen": false,
      "is_off": false,
      "category": "structural",
      "object_count": 234,
      "glb_node_prefix": "S_BEAM"
    },
    {
      "id": "layer-002",
      "name": "M-HVAC-DUCT",
      "color": "#3399FF",
      "color_aci": 5,
      "linetype": "Continuous",
      "lineweight": 0.18,
      "is_frozen": false,
      "is_off": false,
      "category": "mechanical",
      "object_count": 187,
      "glb_node_prefix": "M_HVAC_DUCT"
    }
  ],

  "categories": [
    {
      "id": "structural",
      "label": "구조",
      "label_en": "Structural",
      "color": "#8C8C8C",
      "icon": "beam",
      "object_count": 512,
      "layer_ids": ["layer-001", "layer-003", "layer-004"],
      "visible": true,
      "glb_chunks": ["structural"]
    },
    {
      "id": "mechanical",
      "label": "기계",
      "label_en": "Mechanical",
      "color": "#3399FF",
      "icon": "pipe",
      "object_count": 389,
      "layer_ids": ["layer-002", "layer-007"],
      "visible": true,
      "glb_chunks": ["mechanical"]
    }
  ],

  "objects": [
    {
      "id": "obj-00001",
      "handle": "1A3F",
      "entity_type": "3DSOLID",
      "category": "structural",
      "layer_id": "layer-001",
      "name": "H-BEAM 300×150",
      "glb_node_name": "S_BEAM_1A3F",
      "bounds": {
        "min": { "x": 2.1, "y": -0.075, "z": 3.0 },
        "max": { "x": 8.4, "y":  0.075, "z": 3.3 }
      },
      "properties": {
        "description": "H형강 300×150",
        "material":    "SS400",
        "weight_kg":   125.6,
        "length_m":    6.3,
        "profile":     "H300×150×6.5×9",
        "mark":        "B1-01",
        "elevation_m": 3.0,
        "custom": {
          "spec_ref": "KS D 3503",
          "fabricator": "POSCO"
        }
      }
    },
    {
      "id": "obj-00002",
      "handle": "2B7C",
      "entity_type": "INSERT",
      "category": "mechanical",
      "layer_id": "layer-002",
      "name": "HVAC Duct 600×300",
      "block_name": "DUCT_RECT",
      "glb_node_name": "M_HVAC_2B7C",
      "bounds": {
        "min": { "x": 3.0, "y": 1.2, "z": 4.0 },
        "max": { "x": 9.5, "y": 1.8, "z": 4.3 }
      },
      "properties": {
        "width_mm":  600,
        "height_mm": 300,
        "material":  "Galvanized Steel",
        "insulation": true,
        "flow_direction": "+X",
        "system_id": "AHU-B1-01"
      }
    }
  ]
}
```

### objects_index.json (Unity 클릭 검색용 경량 인덱스)

```json
{
  "version": "1.0",
  "project_id": "550e8400-...",
  "index": {
    "by_node_name": {
      "S_BEAM_1A3F":  "obj-00001",
      "M_HVAC_2B7C":  "obj-00002"
    },
    "by_handle": {
      "1A3F": "obj-00001",
      "2B7C": "obj-00002"
    }
  }
}
```

---

## 6. 주요 API 설계

### 6-1. Upload API

```
POST /api/v1/upload/presign
Authorization: Bearer {jwt}
Content-Type: application/json

Request:
{
  "filename": "office_building.dwg",
  "file_size": 52428800,
  "checksum_md5": "d41d8cd98f00b204e9800998ecf8427e"
}

Response 200:
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "upload_url": "https://s3.amazonaws.com/dwg3d-storage/raw/550e.../original.dwg?X-Amz-...",
  "upload_fields": { "Content-Type": "application/octet-stream" },
  "expires_in": 3600
}

---

POST /api/v1/upload/complete
Authorization: Bearer {jwt}
Content-Type: application/json

Request:
{
  "project_id": "550e8400-...",
  "file_key": "raw/550e.../original.dwg"
}

Response 202:
{
  "job_id": "job-abc123",
  "status": "processing",
  "estimated_minutes": 5,
  "poll_url": "/api/v1/projects/550e8400-.../status"
}
```

### 6-2. Status & Polling API

```
GET /api/v1/projects/{project_id}/status
Authorization: Bearer {jwt}

Response 200:
{
  "project_id": "550e8400-...",
  "status": "converting",
  "progress": {
    "stage":   "aps_convert",
    "percent": 45,
    "message": "3D 모델 변환 중..."
  },
  "stages": [
    { "name": "uploaded",   "status": "done",    "duration_sec": 2 },
    { "name": "aps_upload", "status": "done",    "duration_sec": 18 },
    { "name": "aps_convert","status": "running", "started_at": "..." },
    { "name": "glb_export", "status": "pending" },
    { "name": "analysis",   "status": "pending" },
    { "name": "thumbnail",  "status": "pending" }
  ]
}

---

WebSocket: ws://{host}/api/v1/events/{project_id}
Authorization: Bearer {jwt}  (query param)

Server → Client messages:
{ "type": "progress",  "stage": "aps_convert", "percent": 60 }
{ "type": "complete",  "project_id": "...", "manifest_url": "..." }
{ "type": "error",     "stage": "glb_export",  "message": "..." }
```

### 6-3. Viewer Data API

```
GET /api/v1/projects/{project_id}/manifest
Authorization: Bearer {jwt}

Response 200: manifest.json 내용 전체 반환
(CDN 캐시 가능, Cache-Control: max-age=86400)

---

GET /api/v1/objects/{object_id}
Authorization: Bearer {jwt}

Response 200:
{
  "id": "obj-00001",
  "handle": "1A3F",
  "name": "H-BEAM 300×150",
  "category": "structural",
  "layer": { "id": "layer-001", "name": "S-BEAM" },
  "properties": {
    "description": "H형강 300×150",
    "material":    "SS400",
    "weight_kg":   125.6,
    "length_m":    6.3,
    "mark":        "B1-01"
  },
  "bounds": { "min": {...}, "max": {...} }
}

---

GET /api/v1/objects?project_id={id}&category=structural&layer=S-BEAM
  → 필터 검색 (paginated, limit=100)
```

### 6-4. Internal API (n8n → Worker 호출)

```
POST /internal/v1/convert
X-Internal-Key: {INTERNAL_API_KEY}

Request:
{ "project_id": "...", "file_key": "raw/...", "attempt": 1 }

Response 202:
{ "job_id": "...", "worker_id": "worker-01" }
(비동기 처리, 완료 시 n8n webhook 콜백)

---

POST /internal/v1/analyze
X-Internal-Key: {INTERNAL_API_KEY}

Request:
{ "project_id": "...", "dxf_key": "intermediate/...", "glb_key": "glb/..." }

Response 202: { "job_id": "..." }

---

POST /internal/v1/callback/conversion-complete
X-Internal-Key: {INTERNAL_API_KEY}

Request:
{
  "project_id": "...",
  "job_id": "...",
  "status": "success",
  "glb_keys": { "lod0": "...", "lod1": "...", "lod2": "..." },
  "object_count": 1842,
  "duration_sec": 187
}
```

---

## 7. Unity WebGL 로딩 흐름

### 7-1. 초기화 시퀀스

```
[Unity WebGL 빌드 로드 완료]
  │
  ▼
[AppController.Start()]
  · JSBridge.RegisterCallbacks()  ← JS에서 호출 가능한 함수 등록
  · JSBridge.NotifyReady()        → "unity_ready" 이벤트 발행
  │
  ▼
[Frontend JS가 "unity_ready" 수신]
  · unity.SendMessage("AppController", "LoadProject",
      JSON.stringify({ projectId, manifestUrl, accessToken }))
  │
  ▼
[AppController.LoadProject(json)]
  │
  ▼
[ManifestLoader.Load(manifestUrl)]
  · HTTP GET manifest.json
  · Parse layers[], categories[], assets
  · objects[]는 objects_index.json만 로드 (경량)
  │
  ▼
[로딩 전략 결정]
  · GLB 총 크기 체크
  · < 20MB  → LOD0 단일 로딩
  · 20~50MB → LOD1 먼저 + 백그라운드 LOD0
  · > 50MB  → 카테고리 청크 순차 로딩
  │
  ▼
[ModelLoader.LoadGLB(url, lodLevel)]
  · GLTFast 라이브러리 사용 (Unity 공식 권장)
  · using GLTFast; var gltf = new GltfImport();
  · await gltf.Load(url);
  · await gltf.InstantiateSceneAsync(root_transform);
  │
  ├─ [Progressive Loading] 카테고리별 순차 로딩
  │   1순위: architectural (건축 기본 구조 - 우선 표시)
  │   2순위: structural
  │   3순위: mechanical, electrical, plumbing
  │   각 청크 로드 완료마다 → JSBridge.NotifyChunkLoaded(category)
  │
  ▼
[PostLoad Processing]
  · 각 GameObject에 ObjectData 컴포넌트 부착
    ObjectData { handle, objectId, category, layerId }
  · GLB node name → objects_index로 object_id 매핑
  · MeshRenderer 레퍼런스 수집 → 딕셔너리 캐싱
  │
  ▼
[카메라 초기화]
  · 모델 bounds 계산 (Renderer.bounds 합산)
  · OrbitCamera.FitToView(sceneBounds)
  │
  ▼
[JSBridge.NotifyLoadComplete(stats)]
  → Frontend: "load_complete" 이벤트
  → { object_count, load_time_ms, memory_mb }
```

### 7-2. 객체 클릭 흐름

```
[사용자 클릭]
  │
  ▼
[ObjectPicker.Update()]
  if (Input.GetMouseButtonDown(0) && !IsPointerOverUI())
      Ray ray = Camera.main.ScreenPointToRay(Input.mousePosition)
      if (Physics.Raycast(ray, out hit))
          ObjectData data = hit.collider.GetComponent<ObjectData>()
          if (data != null)
              OnObjectSelected(data)
  │
  ▼
[OnObjectSelected(data)]
  · PreviousHighlight?.ResetMaterial()
  · HighlightController.Highlight(hit.gameObject)
    · 원래 material 저장
    · highlight material 적용 (emission 강조, outline)
  │
  ▼
[JSBridge.NotifyObjectSelected(json)]
  · json = { objectId, handle, glbNodeName, worldPosition }
  │
  ▼
[Frontend JS 수신]
  · fetch /api/v1/objects/{objectId}
  · 상세정보 사이드패널에 표시
```

### 7-3. JS Bridge 설계

```javascript
// bridge.jslib (Unity WebGL Plugin)
mergeInto(LibraryManager.library, {
  NotifyReady: function() {
    window.dispatchEvent(new CustomEvent('unity_ready'));
  },
  NotifyLoadComplete: function(statsJson) {
    const stats = JSON.parse(UTF8ToString(statsJson));
    window.dispatchEvent(new CustomEvent('load_complete', { detail: stats }));
  },
  NotifyObjectSelected: function(dataJson) {
    const data = JSON.parse(UTF8ToString(dataJson));
    window.dispatchEvent(new CustomEvent('object_selected', { detail: data }));
  },
  NotifyChunkLoaded: function(category) {
    window.dispatchEvent(new CustomEvent('chunk_loaded',
      { detail: { category: UTF8ToString(category) } }));
  }
});
```

```csharp
// JSBridge.cs
public class JSBridge : MonoBehaviour {
    // Unity ← JS
    public void SetLayerVisible(string json) {
        var cmd = JsonUtility.FromJson<LayerVisibleCmd>(json);
        // cmd: { layerId, visible }
        LayerFilter.SetVisible(cmd.layerId, cmd.visible);
    }
    public void SetCategoryVisible(string json) {
        var cmd = JsonUtility.FromJson<CategoryVisibleCmd>(json);
        CategoryFilter.SetVisible(cmd.categoryId, cmd.visible);
    }
    public void FocusObject(string objectId) {
        var go = ObjectRegistry.Get(objectId);
        if (go != null) OrbitCamera.FocusOn(go.GetComponent<Renderer>().bounds);
    }
    public void ResetCamera(string _) {
        OrbitCamera.FitToView(SceneBounds.Get());
    }
}
```

---

## 8. WebGL 최적화 전략

### 8-1. 메모리 예산 (WebGL 제약: 총 4GB WASM 힙, 실질 2GB 권장)

```
Unity Heap:      512 MB  (기본 설정)
Texture Memory:  256 MB
Mesh Memory:     512 MB
Code + Runtime:  256 MB
Buffer:          256 MB
─────────────────────
Total:         1,792 MB  (안전 마진 확보)
```

**GLB 크기 목표**:
- LOD0: 50MB 이하 (uncompressed mesh ~150MB)
- Draco 압축 적용 시 파일 크기 70~80% 감소

### 8-2. 메시 최적화

```
Strategy 1: Batching (Draw Call 감소)
  · 같은 material의 static mesh → GPU Instancing
  · 카테고리별 Combined Mesh → 단일 draw call
  · 목표: draw calls < 200/frame

Strategy 2: LOD 전환 기준
  · 카메라 거리 기반:
    0  ~ 20m  → LOD0 (풀 디테일)
    20 ~ 100m → LOD1 (50% 면수)
    100m 이상 → LOD2 (20% 면수)
  · Unity LOD Group 컴포넌트 자동 설정

Strategy 3: Occlusion Culling
  · Unity Umbra Occlusion Culling 활성화
  · 건축물 내부 → 카메라 각도에 따라 반대편 메시 자동 컬링
  · 수동 컬링: AABB frustum 체크로 보완

Strategy 4: 분할 로딩 (Chunk Loading)
  · 초기: LOD2 전체 → 즉시 표시 (< 5MB, 빠른 초기 렌더)
  · 이후: 카테고리별 청크 비동기 로드
  · 카메라 근접 영역 우선 로드 (공간 분할 그리드)

Strategy 5: Texture Atlas
  · 카테고리별 색상은 vertex color로 처리 (텍스처 없음)
  · 텍스처 사용 시: 2048×2048 atlas 1장으로 통합
```

### 8-3. Unity Build 최적화

```
PlayerSettings:
  · WebGL Memory Size: 512 MB
  · Exception Support: None (Release)
  · Compression Format: Brotli (최고 압축률)
  · Strip Engine Code: true
  · Code Optimization: Speed (IL2CPP)
  · Graphics APIs: WebGL 2.0

Build Size 목표:
  · gzip 전: ~40MB
  · gzip 후: ~15MB
  · 초기 로드 시간 (광대역): < 10초
```

---

## 9. 기술 스택 확정

| 레이어 | 기술 | 버전 | 선택 이유 |
|--------|------|------|-----------|
| **Frontend** | Next.js | 14 (App Router) | SSR/SSG, TypeScript, 생태계 |
| **UI** | Tailwind CSS + shadcn/ui | latest | 빠른 UI 개발 |
| **Backend API** | FastAPI (Python) | 0.110+ | 비동기, 타입 힌트, 속도 |
| **Job Queue** | Celery + Redis | 5.x | Python 네이티브 |
| **DWG 변환** | Autodesk Platform Services | v2 | 가장 신뢰성 높은 3D 변환 |
| **DWG 파싱** | ezdxf (Python) | 1.x | DXF 속성/레이어 분석 |
| **3D 처리** | trimesh + numpy | latest | 메시 최적화 |
| **GLB 출력** | pygltflib + draco | latest | Draco 압축 지원 |
| **썸네일** | Blender (headless) | 4.x | 고품질 렌더링 |
| **Unity** | Unity 2022 LTS | 2022.3 | WebGL 안정성 |
| **GLB 로딩** | GLTFast | 6.x | Unity 공식 권장 |
| **DB** | PostgreSQL | 15 | JSONB, pgvector (AI 확장) |
| **Cache** | Redis | 7.x | 잡 큐 + 캐시 |
| **Storage** | AWS S3 | - | 표준, CDN 연계 |
| **CDN** | AWS CloudFront | - | S3 직결, 전세계 배포 |
| **Orchestration** | n8n (self-hosted) | 1.x | 워크플로우 시각화 |
| **Container** | Docker + Docker Compose | - | 개발/배포 일관성 |
| **CI/CD** | GitHub Actions | - | 자동 빌드/배포 |

---

## 10. 기술 리스크 분석

### Risk 1: APS 3D 변환 품질 및 비용 [심각도: HIGH]

```
리스크:
  · 복잡한 ACIS/ShapeManager 3D 솔리드가 APS에서 잘못 변환될 수 있음
  · APS 비용: Model Derivative 처리당 과금 (대형 파일 $0.1~$0.5)
  · APS 레이트 리밋: 기본 10 req/min (엔터프라이즈 필요 시 협의)

완화 전략:
  · 변환 후 품질 체크: 예상 bound와 실제 bound 비교 (20% 이상 차이 시 경고)
  · ODA File Converter (무료, 오프라인) 병행 옵션 유지
  · 비용 모니터링: AWS Cost Explorer + n8n 알림
  · 캐싱: 동일 파일(checksum 기준) 재변환 방지

APS 대안 (만약 비용/품질 이슈 발생 시):
  · ODA Web Services (구독형, 연간 계약)
  · Open CASCADE + FreeCad CLI (오픈소스, 품질 제한)
  · Aspose.CAD (상용, .NET 기반)
```

### Risk 2: WebGL 메모리 한계 [심각도: HIGH]

```
리스크:
  · 대형 DWG (500MB+) → GLB 변환 후 100MB+ 가능
  · WebGL WASM 힙 2GB 제한 초과 시 크래시
  · 모바일 브라우저: 실질 256MB~512MB 제한

완화 전략:
  · 서버에서 LOD 생성 + Draco 압축 → 파일 크기 90% 감소 목표
  · 카테고리 청크 분할 로딩 → 한 번에 50MB 이하만 로딩
  · 메모리 사용량 모니터링: performance.memory API
  · 임계값 초과 시 하위 LOD로 자동 전환
  · 공간 분할: 카메라 Frustum 밖 청크 언로드 (Addressables 활용)
```

### Risk 3: DWG 버전/기능 호환성 [심각도: MEDIUM]

```
리스크:
  · DWG 포맷은 AutoCAD R14 ~ 2024 까지 다양 (AC1014 ~ AC1043)
  · 일부 서드파티 CAD 소프트웨어 생성 DWG: 비표준 확장 포함
  · 외부 참조 (XREF) 포함 파일: 단일 파일로 처리 불가

완화 전략:
  · APS는 AC1015~AC1032 (R2000~R2018) 공식 지원
  · 업로드 시 버전 체크 + 지원 범위 안내
  · XREF 감지 시: "외부 참조 파일을 함께 업로드해주세요" 안내
  · DWG 버전 너무 오래된 경우 (< AC1015): 변환 거부 + 안내
```

### Risk 4: 변환 처리 시간 [심각도: MEDIUM]

```
리스크:
  · APS 변환: 대형 파일 30분+ 가능
  · 사용자 경험 저하 (장시간 대기)
  · APS 서비스 장애 시 파이프라인 전체 중단

완화 전략:
  · WebSocket 실시간 진행률 표시 (단계별 %)
  · 이메일/알림 푸시: "변환 완료 시 알림"
  · APS Timeout 60분 설정, 초과 시 자동 실패 처리
  · n8n 재시도 로직 (최대 3회, exponential backoff)
  · APS 장애 시: ODA Cloud API 폴백 (설정 토글)
```

### Risk 5: Unity WebGL 로딩 성능 [심각도: MEDIUM]

```
리스크:
  · 첫 방문 시 Unity WebGL 빌드 다운로드 (~15MB)
  · GLTFast 파싱 시간: 50MB GLB → 3~10초 (CPU 사양 따라)
  · 모바일 Safari: WebGL 2.0 일부 기능 제한

완화 전략:
  · Unity Build: Brotli 압축 + CDN 캐싱 (재방문 시 즉시 로드)
  · Progressive Loading: LOD2(5MB) 먼저 표시 → 점진적 교체
  · ServiceWorker: Unity build 오프라인 캐싱
  · 모바일 감지 시: 저사양 모드 (LOD2 고정, culling 강화)
```

### Risk 6: n8n 단일 실패점 [심각도: LOW-MEDIUM]

```
리스크:
  · n8n 장애 시 변환 파이프라인 전체 중단
  · n8n 상태가 DB와 불일치 가능

완화 전략:
  · n8n 컨테이너: health check + 자동 재시작 (Docker restart: always)
  · n8n 외 백업 경로: 직접 Worker HTTP 호출 (n8n 우회 모드)
  · 상태 체크: 30분 이상 processing 상태 → 자동 재시도 cron
  · n8n PostgreSQL 백업: 일일 자동 백업
```

---

## 11. 4주 MVP 개발 로드맵

### Week 1: 인프라 + 기반 파이프라인

```
Day 1-2: 인프라 셋업
  [ ] Docker Compose 환경 구성
      · FastAPI (main API)
      · FastAPI (conversion worker)
      · PostgreSQL
      · Redis
      · n8n
  [ ] AWS S3 버킷 생성 + IAM 설정
  [ ] PostgreSQL 스키마 마이그레이션 (Alembic)
  [ ] GitHub Actions: lint + test 파이프라인

Day 3-4: DWG → GLB 파이프라인 (핵심)
  [ ] APS 계정 설정 + API 키 발급
  [ ] APS 업로드 + 변환 Job 제출 Python 모듈 작성
  [ ] APS 상태 폴링 + OBJ 다운로드
  [ ] trimesh OBJ → GLB 변환 + S3 업로드
  [ ] 테스트 DWG 파일 10개로 변환 검증

Day 5: ezdxf 파싱 + manifest.json 생성
  [ ] Layer 추출
  [ ] 카테고리 분류 로직
  [ ] manifest.json 스키마 구현
  [ ] S3 저장

산출물: DWG → GLB + manifest.json 자동 생성 스크립트
```

### Week 2: API 서버 + n8n 오케스트레이션

```
Day 6-7: 메인 API 서버 (FastAPI)
  [ ] POST /upload/presign (Presigned URL 생성)
  [ ] POST /upload/complete (업로드 완료 처리)
  [ ] GET  /projects/{id}/status
  [ ] GET  /projects/{id}/manifest
  [ ] GET  /objects/{id}
  [ ] WebSocket /events/{project_id}
  [ ] JWT 인증 미들웨어

Day 8-9: n8n 워크플로우 구성
  [ ] Workflow 1: Upload Trigger
  [ ] Workflow 2: 변환 완료 후처리
  [ ] Workflow 3: 실패 재시도
  [ ] Slack 알림 연동
  [ ] 썸네일 생성 트리거

Day 10: Celery 잡 큐 + Worker
  [ ] Celery + Redis 설정
  [ ] conversion_task, analysis_task, thumbnail_task 구현
  [ ] n8n → Worker HTTP API 연결

산출물: 완전한 변환 파이프라인 (파일 업로드 → GLB + JSON → 알림)
```

### Week 3: Unity WebGL 뷰어

```
Day 11-12: Unity 프로젝트 셋업 + GLB 로딩
  [ ] Unity 2022 LTS 프로젝트 생성
  [ ] GLTFast 패키지 설치
  [ ] ModelLoader.cs: manifest URL → GLB 로딩
  [ ] 기본 씬 구성 (카메라, 라이팅)

Day 13: 카메라 + 인터랙션
  [ ] OrbitCamera.cs (Orbit / Pan / Zoom)
  [ ] ObjectPicker.cs (Raycast 클릭)
  [ ] HighlightController.cs (하이라이트 효과)
  [ ] ObjectData 컴포넌트

Day 14: 필터 시스템
  [ ] LayerFilter.cs (레이어 숨김/표시)
  [ ] CategoryFilter.cs (카테고리 필터)

Day 15: JS Bridge + WebGL 빌드
  [ ] bridge.jslib 구현
  [ ] JSBridge.cs (SendMessage 양방향 통신)
  [ ] WebGL 빌드 생성 + S3/CDN 배포
  [ ] 빌드 크기 최적화 (목표: gzip 후 15MB)

산출물: 동작하는 Unity WebGL 뷰어 (GLB 로딩 + 클릭 + 필터)
```

### Week 4: 프론트엔드 + 통합 + 최적화

```
Day 16-17: Next.js 프론트엔드
  [ ] 프로젝트 목록 페이지
  [ ] 파일 업로드 UI (drag & drop, 진행률)
  [ ] 뷰어 페이지 (Unity WebGL iframe 임베드)
  [ ] 레이어/카테고리 패널 (sidebar)
  [ ] 상세정보 사이드패널
  [ ] WebSocket 연결 + 실시간 진행 상태

Day 18: Unity ↔ Frontend 통신 통합
  [ ] JS Bridge 메시지 연결 (object_selected 등)
  [ ] 레이어 패널 토글 → Unity 전달
  [ ] 카테고리 필터 → Unity 전달
  [ ] 오브젝트 클릭 → API 조회 → 패널 표시

Day 19: 최적화 + 버그 수정
  [ ] LOD 전환 구현 (Unity LOD Group)
  [ ] 청크 분할 로딩 구현
  [ ] WebGL 메모리 사용량 테스트
  [ ] 실제 DWG 5개 End-to-End 테스트

Day 20: 배포 + 문서화
  [ ] Docker Compose → AWS ECS 또는 EC2 배포
  [ ] 환경변수 / secrets 관리 (.env)
  [ ] 기본 사용자 인증 (JWT, 회원가입/로그인)
  [ ] README 업데이트 + API 문서 (FastAPI 자동 생성)

산출물: 동작하는 MVP SaaS 서비스
```

### MVP 이후 확장 로드맵 (AI 연동 준비)

```
5주차 이후:
  [ ] pgvector 기반 객체 임베딩 저장
      → 객체 설명 text → embedding → 유사 객체 검색
  [ ] AI 구조 추론 API 연동 포인트
      POST /api/v1/ai/classify?project_id=...
      → 레이어명 없이 geometry로 카테고리 추론
  [ ] Streaming 분할 로딩 (큰 모델 공간 분할)
  [ ] 사용자별 뷰 설정 저장
  [ ] 협업 기능 (동시 뷰어, 코멘트)
  [ ] 자동 설계 검토 (충돌 감지, 클리어런스 체크)
```

---

## 부록: 핵심 의사결정 요약

| 결정 | 선택 | 대안 | 이유 |
|------|------|------|------|
| DWG 3D 변환 | APS Model Derivative | ODA SDK, Open CASCADE | 가장 신뢰성, SaaS 형태 |
| DWG 속성 파싱 | ezdxf | LibreDWG | Python 네이티브, 활발한 유지보수 |
| 중간 포맷 | GLB (Binary glTF) | FBX, USDZ | 웹 표준, Draco 압축, Unity 지원 |
| Unity GLB 로더 | GLTFast | Trilib 2 | Unity 공식 지원, 무료 |
| 오케스트레이션 | n8n | Airflow, Temporal | 코딩 없이 워크플로우, UI 제공 |
| DB | PostgreSQL + JSONB | MongoDB | 관계형 + 유연한 속성 저장 양립 |
| 3D 메시 처리 | trimesh | Open3D, Blender API | 경량, pip 설치, Python 친화 |
