from __future__ import annotations

import asyncio
from typing import Optional

import strawberry

from app.scheduler import _run_ingestion_async, _run_venue_enrichment_async


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def start_ingestion(self) -> str:
        asyncio.create_task(_run_ingestion_async())
        return "ingestion started"

    @strawberry.mutation
    async def refresh_venue_enrichment(self, venue_id: Optional[strawberry.ID] = None) -> str:
        asyncio.create_task(_run_venue_enrichment_async(int(venue_id) if venue_id else None))
        target = f"venue {venue_id}" if venue_id else "all venues"
        return f"venue enrichment started for {target}"
