# DWG3D

> DWG(3D 포함) 업로드 → 분석/가공 파이프라인 → Unity WebGL 시각화 + 필터 + 상세정보

## 개요

DWG3D는 AutoCAD DWG/DXF 파일(3D 객체 포함)을 업로드하면, 자동 분석/가공 파이프라인을 통해 GLB로 변환하고 Unity WebGL 기반 인터랙티브 3D 뷰어로 시각화하는 SaaS 플랫폼입니다.

```
DWG / DXF 업로드
       │
       ▼
 분석/가공 파이프라인 (n8n 오케스트레이션)
  ├─ APS Model Derivative (DWG → OBJ)
  ├─ trimesh 후처리 (OBJ → GLB + LOD)
  ├─ ezdxf 파싱 (레이어/속성 → manifest.json)
  └─ Blender 썸네일 생성
       │
       ▼
Unity WebGL 시각화
  ├─ Orbit 카메라 (Pan / Zoom / Rotate)
  ├─ 객체 클릭 하이라이트
  ├─ 카테고리 필터 (구조/기계/전기/건축/배관)
  ├─ 레이어 숨김/표시
  └─ 클릭 시 상세정보 패널
```

## 기술 스택

| 레이어 | 기술 |
|--------|------|
| **Frontend** | Next.js 14 + Tailwind CSS + shadcn/ui |
| **Backend API** | FastAPI (Python) |
| **DWG 변환** | Autodesk Platform Services (APS) Model Derivative |
| **DWG 파싱** | ezdxf |
| **3D 메시 처리** | trimesh + numpy |
| **GLB 출력** | pygltflib + Draco 압축 |
| **Unity WebGL** | Unity 2022 LTS + GLTFast |
| **오케스트레이션** | n8n (self-hosted) |
| **Job Queue** | Celery + Redis |
| **Database** | PostgreSQL 15 (JSONB + pgvector) |
| **Storage** | AWS S3 + CloudFront |
| **썸네일** | Blender headless |

## 프로젝트 구조

```
DWG3D/
├── backend/           # FastAPI API 서버 + 변환 워커
│   ├── api/           # 메인 API (upload, status, manifest)
│   ├── workers/       # Celery 워커 (conversion, analysis, thumbnail)
│   └── core/          # 공통 유틸 (APS, S3, DB)
├── frontend/          # Next.js 웹 클라이언트
│   ├── app/           # App Router 페이지
│   └── components/    # UI 컴포넌트
├── unity/             # Unity WebGL 프로젝트
│   └── Assets/
│       └── Scripts/   # C# 스크립트 (Camera, Bridge, Filter, LOD)
├── n8n/               # n8n 워크플로우 정의 (JSON export)
├── docs/
│   └── architecture.md  # ← 전체 아키텍처 설계서 (상세)
├── docker-compose.yml
└── README.md
```

## 아키텍처

**전체 설계서**: [docs/architecture.md](docs/architecture.md)

설계서에 포함된 내용:
- 전체 시스템 다이어그램 (계층별)
- DWG → GLB 변환 파이프라인 (6단계 상세)
- n8n 오케스트레이션 워크플로우 설계
- 구조 JSON 설계 (manifest.json 전체 예시)
- 주요 API 설계 (Upload, Status, Viewer, Internal)
- Unity WebGL 로딩 흐름 + JS Bridge 설계
- WebGL 최적화 전략 (LOD, Culling, 청크 로딩)
- 기술 리스크 분석 (6개 항목)
- 4주 MVP 개발 로드맵

## 변환 데이터 흐름

```
[1] 사용자 DWG 업로드 (S3 Presigned URL 직접 업로드)
[2] n8n 트리거 → Conversion Worker 실행
[3] APS Model Derivative: DWG → OBJ (단위: meter)
[4] trimesh: OBJ → 메시 최적화 → GLB (LOD0/1/2) + Draco 압축
[5] ezdxf: DXF 파싱 → 레이어/카테고리/속성 → manifest.json
[6] Blender headless: 썸네일 PNG 생성
[7] 모든 파일 S3 저장 + CloudFront CDN 캐싱
[8] WebSocket으로 완료 알림 → Unity WebGL 로딩 시작
[9] Unity: LOD2 선로딩 → 점진적 청크 로딩 → 인터랙션 활성화
```

## MVP 기능 범위

- **파일 업로드**: DWG/DXF 업로드 (최대 500MB), 실시간 진행률
- **3D 뷰어**: Unity WebGL 기반, Orbit 카메라 컨트롤
- **객체 선택**: 클릭 하이라이트 + 속성 정보 패널
- **카테고리 필터**: 구조/기계/전기/건축/배관 분류별 ON/OFF
- **레이어 필터**: DWG 레이어별 숨김/표시
- **썸네일**: 프로젝트 목록에 3D 모델 미리보기

## 시작하기

```bash
# 환경변수 설정
cp .env.example .env
# APS_CLIENT_ID, APS_CLIENT_SECRET, AWS_* 설정 필요

# 전체 스택 실행 (개발)
docker compose up -d

# API 서버: http://localhost:8000
# n8n:      http://localhost:5678
# Frontend: http://localhost:3000
```

> 상세 실행 가이드는 각 디렉토리 README 참고 (구현 진행에 따라 업데이트)

## 라이선스

MIT
