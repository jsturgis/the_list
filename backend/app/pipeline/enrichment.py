"""LangChain enrichment chain: genre tags, Spotify/SoundCloud, venue website, ticket URL."""
from app.ingestion.parser import RawShow
from app.pipeline.providers import get_enrichment_llm


async def enrich_show(raw: RawShow) -> dict:
    """Enrich a RawShow with genre tags, streaming links, venue website, and ticket URL.

    Returns a dict matching the Show + Band schema fields ready for upsert.
    """
    # TODO: implement sequential chain:
    #   1. LLM: extract structured fields + genre tags from raw_text
    #   2. Spotify API: search headliner → spotify_url (SoundCloud fallback)
    #   3. Search: venue website
    #   4. Ticketing: venue site → Eventbrite → Ticketmaster for ticket_url
    raise NotImplementedError
