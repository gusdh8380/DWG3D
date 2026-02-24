# DWG3D Architecture

## 시스템 개요

```
[사용자]
   │
   ▼
[Frontend]
  ├─ DWG / DWG3D 파일 업로드 UI
  ├─ Unity WebGL 뷰어 임베드
  ├─ 필터 패널 (레이어, 타입, 속성 등)
  └─ 상세정보 사이드패널
   │
   ▼
[Backend API]
  ├─ 파일 수신 및 저장
  ├─ DWG 파싱 (2D/3D)
  ├─ 분석 파이프라인
  │   ├─ 엔티티 추출 (선, 호, 폴리선, 솔리드 등)
  │   ├─ 메타데이터 파싱 (레이어, 블록, 속성)
  │   └─ 3D 지오메트리 변환
  └─ Unity 전달용 포맷 변환 (JSON / glTF)
   │
   ▼
[Unity WebGL Build]
  ├─ 3D/2D 렌더링
  ├─ 카메라 컨트롤 (Pan / Zoom / Rotate)
  ├─ 레이어/오브젝트 필터링
  └─ 오브젝트 선택 → 상세정보 이벤트 전송
```

## 데이터 흐름

1. 사용자가 `.dwg` 또는 `.dxf` 파일 업로드
2. Backend가 파일을 파싱하여 엔티티/레이어/속성 추출
3. 추출된 데이터를 Unity 호환 포맷으로 변환
4. Frontend Unity WebGL 뷰어에서 렌더링
5. 사용자가 오브젝트 선택 시 상세정보 패널에 속성 표시

## 주요 컴포넌트 (TBD)

| 레이어 | 기술 스택 | 상태 |
|--------|----------|------|
| Frontend | TBD | 계획 중 |
| Backend | TBD | 계획 중 |
| DWG 파서 | TBD | 계획 중 |
| Unity WebGL | Unity (C#) | 계획 중 |
| 스토리지 | TBD | 계획 중 |
| DB | TBD | 계획 중 |
