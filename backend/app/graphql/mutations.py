from __future__ import annotations

import asyncio
import strawberry

from app.scheduler import _run_ingestion_async


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def start_ingestion(self) -> str:
        asyncio.create_task(_run_ingestion_async())
        return "ingestion started"
