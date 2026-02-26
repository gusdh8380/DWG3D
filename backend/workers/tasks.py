"""
Celery 변환 태스크
DXF/DWG 파일을 다운로드하여 파이프라인을 실행하고 결과를 S3에 업로드한다.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from celery import Task
from sqlalchemy.orm import Session

from workers.celery_app import app
from app.core.config import settings
from app.core.database import get_sync_db
from app.core.storage import download_to_file, upload_bytes, object_public_url
from app.models import Project, ConversionJob, Layer, DwgObject  # noqa: F401 — 전체 임포트로 mapper 초기화
from pipeline.dxf_parser import parse_dxf
from pipeline.mock_aps import generate_mock_scene
from pipeline.glb_exporter import export_glb
from pipeline.manifest_builder import build_manifest, build_objects_index

logger = logging.getLogger(__name__)

# ─── 상태 정의 ────────────────────────────────────────────────────────────────
STAGES = [
    "download",
    "convert",
    "export_glb",
    "build_manifest",
    "upload",
]


def _update_project(db: Session, project_id: str, **kwargs) -> None:
    db.query(Project).filter(Project.id == project_id).update(kwargs)
    db.commit()


def _log_job(db: Session, project_id: str, stage: str, status: str, log: str = "") -> None:
    job = ConversionJob(
        project_id=project_id,
        stage=stage,
        status=status,
        started_at=datetime.now(tz=timezone.utc) if status == "running" else None,
        finished_at=datetime.now(tz=timezone.utc) if status in ("done", "failed") else None,
        log=log[:4000] if log else None,
    )
    db.add(job)
    db.commit()


# ─── 메인 변환 태스크 ─────────────────────────────────────────────────────────

@app.task(bind=True, name="workers.tasks.convert_file_task", max_retries=3)
def convert_file_task(self: Task, project_id: str) -> dict:
    """
    DXF/DWG 파일을 GLB + manifest.json 으로 변환한다.

    Args:
        project_id: 프로젝트 UUID (str)

    Returns:
        결과 요약 dict
    """
    db = get_sync_db()
    os.makedirs(settings.temp_dir, exist_ok=True)

    try:
        # ── 프로젝트 로드 ──────────────────────────────────────────────────────
        project: Project = db.query(Project).filter(
            Project.id == project_id
        ).first()

        if not project:
            raise ValueError(f"Project not found: {project_id}")

        _update_project(db, project_id, status="processing")
        logger.info(f"[{project_id}] 변환 시작: {project.original_name}")

        # ── Stage 1: 파일 다운로드 ────────────────────────────────────────────
        _log_job(db, project_id, "download", "running")
        ext = project.file_type or "dxf"

        with tempfile.NamedTemporaryFile(
            suffix=f".{ext}", dir=settings.temp_dir, delete=False
        ) as tmp:
            tmp_path = tmp.name

        try:
            download_to_file(project.file_key, tmp_path)
            _log_job(db, project_id, "download", "done")
            logger.info(f"[{project_id}] 파일 다운로드 완료: {tmp_path}")

            # ── Stage 2: 파일 변환 (Parse) ────────────────────────────────────
            _update_project(db, project_id, status="converting")
            _log_job(db, project_id, "convert", "running")

            if ext == "dxf" and not settings.use_mock_conversion:
                parse_result = parse_dxf(tmp_path)
                logger.info(f"[{project_id}] DXF 파싱 완료")
            else:
                # DWG 또는 mock 모드: 절차적 씬 생성
                parse_result = generate_mock_scene(project.name)
                logger.info(f"[{project_id}] Mock 씬 생성 완료")

            _log_job(db, project_id, "convert", "done",
                     f"objects={len(parse_result.objects)}")

            # ── Stage 3: GLB 익스포트 ─────────────────────────────────────────
            _update_project(db, project_id, status="exporting")
            _log_job(db, project_id, "export_glb", "running")

            glb_result = export_glb(parse_result.geometries)
            logger.info(
                f"[{project_id}] GLB 익스포트 완료: "
                f"lod0={len(glb_result.lod0)//1024}KB, "
                f"lod1={len(glb_result.lod1)//1024}KB, "
                f"lod2={len(glb_result.lod2)//1024}KB"
            )
            _log_job(db, project_id, "export_glb", "done",
                     f"faces={glb_result.total_faces}")

            # ── Stage 4: Manifest 생성 ────────────────────────────────────────
            _log_job(db, project_id, "build_manifest", "running")

            # S3 키 정의
            pid = str(project_id)
            glb_lod0_key = f"glb/{pid}/model_lod0.glb"
            glb_lod1_key = f"glb/{pid}/model_lod1.glb"
            glb_lod2_key = f"glb/{pid}/model_lod2.glb"
            manifest_key = f"json/{pid}/manifest.json"
            index_key    = f"json/{pid}/objects_index.json"

            asset_urls = {
                "lod0":          object_public_url(glb_lod0_key),
                "lod1":          object_public_url(glb_lod1_key),
                "lod2":          object_public_url(glb_lod2_key),
                "objects_index": object_public_url(index_key),
                "thumbnail":     "",  # 썸네일은 별도 태스크
            }

            manifest = build_manifest(
                project_id=project_id,
                project_name=project.name,
                source_filename=project.original_name,
                parse_result=parse_result,
                asset_urls=asset_urls,
            )
            obj_index = build_objects_index(parse_result)
            _log_job(db, project_id, "build_manifest", "done")

            # ── Stage 5: S3 업로드 ────────────────────────────────────────────
            _update_project(db, project_id, status="uploading")
            _log_job(db, project_id, "upload", "running")

            upload_bytes(glb_lod0_key, glb_result.lod0, "model/gltf-binary")
            upload_bytes(glb_lod1_key, glb_result.lod1, "model/gltf-binary")
            upload_bytes(glb_lod2_key, glb_result.lod2, "model/gltf-binary")
            upload_bytes(manifest_key, json.dumps(manifest, ensure_ascii=False).encode(), "application/json")
            upload_bytes(index_key,    json.dumps(obj_index, ensure_ascii=False).encode(), "application/json")

            _log_job(db, project_id, "upload", "done")
            logger.info(f"[{project_id}] S3 업로드 완료")

            # ── DB 업데이트 (완료) ────────────────────────────────────────────
            _update_project(
                db, project_id,
                status="complete",
                glb_key=glb_lod0_key,
                glb_lod1_key=glb_lod1_key,
                glb_lod2_key=glb_lod2_key,
                manifest_key=manifest_key,
                object_count=len(parse_result.objects),
                completed_at=datetime.now(tz=timezone.utc),
            )

            # ── DB 오브젝트/레이어 저장 ───────────────────────────────────────
            _save_objects_to_db(db, project_id, parse_result)

            logger.info(f"[{project_id}] 변환 완료!")
            return {
                "project_id": pid,
                "status": "complete",
                "object_count": len(parse_result.objects),
                "glb_lod0_key": glb_lod0_key,
            }

        finally:
            # 임시 파일 정리
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    except Exception as exc:
        logger.error(f"[{project_id}] 변환 실패: {exc}", exc_info=True)
        _update_project(db, project_id, status="failed", error_msg=str(exc)[:500])
        try:
            self.retry(exc=exc, countdown=60 * (self.request.retries + 1))
        except self.MaxRetriesExceededError:
            pass
        raise

    finally:
        db.close()


def _save_objects_to_db(db: Session, project_id: str, parse_result) -> None:
    """레이어와 오브젝트를 DB에 저장한다."""
    # 레이어 저장
    layer_orm_map: dict[str, Layer] = {}
    for pl in parse_result.layers:
        layer = Layer(
            id=pl.id,
            project_id=project_id,
            name=pl.name,
            color=pl.color_hex,
            color_aci=pl.color_aci,
            is_frozen=pl.is_frozen,
            is_off=pl.is_off,
            category=pl.category,
            object_count=pl.object_count,
        )
        db.add(layer)
        layer_orm_map[pl.name] = layer

    db.flush()

    # 오브젝트 저장 (최대 5000개, MVP 제한)
    for obj in parse_result.objects[:5000]:
        layer_orm = layer_orm_map.get(obj.layer_name)
        db.add(DwgObject(
            id=obj.id,
            project_id=project_id,
            layer_id=layer_orm.id if layer_orm else None,
            handle=obj.handle,
            entity_type=obj.entity_type,
            category=obj.category,
            name=obj.name,
            glb_node_name=obj.glb_node_name,
            bounds=obj.bounds,
            properties=obj.properties,
        ))

    db.commit()
    logger.info(f"[{project_id}] DB 저장 완료: "
                f"layers={len(parse_result.layers)}, objects={len(parse_result.objects)}")
