"""
DB 초기화 스크립트 (Docker 컨테이너 시작 시 실행)
테이블이 없으면 생성한다.
"""
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    from app.core.database import create_tables
    logger.info("DB 테이블 초기화 중...")
    await create_tables()
    logger.info("DB 초기화 완료")


if __name__ == "__main__":
    asyncio.run(main())
