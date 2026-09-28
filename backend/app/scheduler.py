"""APScheduler weekly ingestion job — fires every Friday at 6 PM."""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

scheduler = BackgroundScheduler()


def run_ingestion_pipeline() -> None:
    """Full pipeline: fetch email → parse → enrich → embed → upsert → save FAISS indices."""
    # TODO: wire ingestion.gmail → ingestion.parser → pipeline.enrichment
    #       → embeddings.client → embeddings.indexer → DB upsert
    raise NotImplementedError


scheduler.add_job(
    run_ingestion_pipeline,
    CronTrigger(day_of_week="fri", hour=18, minute=0),
    id="weekly_ingestion",
    replace_existing=True,
)
