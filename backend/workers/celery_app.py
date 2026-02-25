from celery import Celery
from app.core.config import settings

app = Celery(
    "dwg3d",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["workers.tasks"],
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Seoul",
    enable_utc=True,
    task_routes={
        "workers.tasks.convert_file_task": {"queue": "conversion"},
    },
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
)
