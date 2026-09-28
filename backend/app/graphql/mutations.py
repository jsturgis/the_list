from __future__ import annotations

import strawberry
from fastapi import BackgroundTasks
from strawberry.types import Info

from app.scheduler import _run_ingestion_async


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def start_ingestion(self, info: Info) -> str:
        background_tasks: BackgroundTasks = info.context["background_tasks"]
        background_tasks.add_task(_run_ingestion_async)
        return "ingestion started"
