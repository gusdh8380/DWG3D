"""
DWG3D — FastAPI 메인 애플리케이션
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import create_tables
from app.api.v1 import upload, projects, objects

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── 시작 시 ───────────────────────────────────────────────────────────────
    logger.info("DWG3D API 서버 시작 중...")
    await create_tables()
    logger.info("DB 테이블 준비 완료")
    yield
    # ── 종료 시 ───────────────────────────────────────────────────────────────
    logger.info("DWG3D API 서버 종료")


app = FastAPI(
    title="DWG3D API",
    description="DWG(3D 포함) 업로드 → GLB 변환 → Unity WebGL 시각화 SaaS",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS (개발 환경: 전체 허용) ───────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 라우터 등록 ───────────────────────────────────────────────────────────────
PREFIX = "/api/v1"
app.include_router(upload.router,   prefix=PREFIX)
app.include_router(projects.router, prefix=PREFIX)
app.include_router(objects.router,  prefix=PREFIX)


# ── 헬스체크 ─────────────────────────────────────────────────────────────────
@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok", "service": "DWG3D API", "version": "0.1.0"}


@app.get("/", tags=["system"])
async def root():
    return {
        "message": "DWG3D API",
        "docs": "/docs",
        "health": "/health",
    }
