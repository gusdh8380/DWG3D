# DWG3D

> DWG(3D 포함) 업로드 → 분석/가공 파이프라인 → Unity WebGL 시각화 + 필터 + 상세정보

## 개요

DWG3D는 AutoCAD DWG/DXF 파일(2D 및 3D)을 업로드하고, 자동 분석/가공 파이프라인을 통해 Unity WebGL 기반 인터랙티브 뷰어로 시각화하는 플랫폼입니다.

```
DWG / DXF 업로드
       │
       ▼
 분석/가공 파이프라인
  ├─ 엔티티 추출
  ├─ 레이어/속성 파싱
  └─ 3D 지오메트리 변환
       │
       ▼
Unity WebGL 시각화
  ├─ 3D/2D 렌더링
  ├─ 레이어 필터
  └─ 오브젝트 상세정보
```

## 주요 기능

- **파일 업로드**: `.dwg`, `.dxf` 포맷 지원 (2D/3D)
- **자동 분석**: 레이어, 블록, 엔티티, 속성 자동 추출
- **Unity WebGL 뷰어**: 브라우저에서 바로 3D/2D 도면 시각화
- **레이어 필터**: 레이어/타입/속성별 표시/숨김 제어
- **오브젝트 상세정보**: 선택한 오브젝트의 속성 정보 표시

## 프로젝트 구조

```
DWG3D/
├── backend/        # 파일 처리 API 서버 (TBD)
├── frontend/       # 웹 클라이언트 (TBD)
├── unity/          # Unity WebGL 프로젝트
├── docs/           # 문서
│   └── architecture.md
├── .github/
│   └── workflows/  # CI/CD
└── README.md
```

## 아키텍처

자세한 내용은 [docs/architecture.md](docs/architecture.md)를 참조하세요.

## 기술 스택

| 레이어 | 기술 | 상태 |
|--------|------|------|
| Frontend | TBD | 계획 중 |
| Backend | TBD | 계획 중 |
| Unity WebGL | Unity (C#) | 계획 중 |
| DWG 파서 | TBD | 계획 중 |

## 시작하기

> 기술 스택 결정 후 업데이트 예정

## 라이선스

MIT
