"""Which tags are genres. Last.fm's tags and MusicBrainz's free-form tags are user tagging: next to "egg punk" and
"youth crew" they hold places ("united states", "east bay"), nationalities ("finnish"), instruments ("banjo"),
moods ("mellow") and notes ("seen live", "my top songs"). Only genres are kept.

A tag is a genre when it's in the vocabulary: MusicBrainz's curated genres (genres.txt) plus a few common
shorthands they spell out ("rnb", "alt-country"), matched ignoring case, spacing and punctuation ("synthpop" is
"synth-pop"). Anything else is asked of a small decision model on Ollama (settings.genre_model, a JEV-style model
answered through /v1/systemone), and its answer is kept in the genre_tags table, so each tag is judged once and
a wrong call can be corrected by editing its row.

When the model can't be reached, nothing is recorded and it isn't asked again that run. The backfill raises
GenreModelUnavailable (the Band fails and is tried again next run); the ingest keeps unknown tags as they are
for that run (logged), rather than lose them for good, for a later `backfill --recheck-genres` to clean up.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from datetime import datetime
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models.genre_tag import GenreTag

logger = logging.getLogger(__name__)

# Shorthands for genres MusicBrainz names in full, and broad genres it doesn't list, as keys (see key()).
_ALIASES = {
    "rnb", "randb", "altcountry", "altrock", "alternativernb", "standup", "hiphop", "rap", "goth", "doom",
    "sludge", "stoner", "stonerdoom", "crust", "jam", "indie", "alternative", "hardcore", "punkrock", "prog",
}
_QUESTION = ("Is this Last.fm tag the name of a music genre or style? Answer no for places, nationalities, "
             "instruments, people, bands, record labels, TV shows, moods, and personal notes like seen live.")


def key(tag: str) -> str:
    """A tag compared ignoring case, spacing and punctuation: "Synth-Pop", "synthpop" and "synth pop" are one."""
    tag = tag.lower().replace("&", "and").replace("'n'", "and")
    return re.sub(r"[^a-z0-9]", "", tag)


def _vocabulary() -> frozenset[str]:
    lines = (Path(__file__).with_name("genres.txt").read_text().splitlines())
    return frozenset(key(line) for line in lines if line.strip() and not line.startswith("#")) | _ALIASES


VOCABULARY = _vocabulary()


def ask_model(tag: str, attempts: int = 3) -> float | None:
    """The model's probability that `tag` is a genre, or None when it can't be asked. Tried a few times: Ollama's
    runner sometimes crashes on one request and restarts."""
    for attempt in range(attempts):
        try:
            response = httpx.post(f"{settings.ollama_base_url}/v1/systemone", timeout=30, json={
                "model": settings.genre_model,
                "state": {"tag": tag},
                "questions": {"genre": {"type": "noul", "instructions": _QUESTION}},
            })
            return float(response.raise_for_status().json()["answers"]["genre"]["noul"])
        except Exception:
            if attempt == attempts - 1:
                logger.warning("genres: couldn't ask %s about %r", settings.genre_model, tag, exc_info=True)
                return None
            time.sleep(2)
    return None


def genre_model_problem() -> str | None:
    """Why the genre model can't be asked (Ollama unreachable or too old, the model not pulled), or None."""
    if ask_model("death metal") is None:
        return f"couldn't ask the genre model {settings.genre_model} on Ollama at {settings.ollama_base_url} (needs 0.35+)"
    return None


class GenreModelUnavailable(RuntimeError):
    """The genre model can't be asked, so whether a tag is a genre can't be told."""


class GenreFilter:
    """Keeps the genres among tags (see the module docstring). Load it from the database at the start of a run
    and save() it after: it can be used from worker threads in between.

    `keep_unknown` (the ingest) keeps a tag the model can't judge; otherwise is_genre raises GenreModelUnavailable.
    """

    def __init__(self, decisions: dict[str, bool] | None = None, keep_unknown: bool = False):
        self._decisions = dict(decisions or {})
        self._new: list[GenreTag] = []
        self._lock = threading.Lock()
        self._keep_unknown = keep_unknown
        self._model_down = False  # after one failure the model isn't asked again this run

    @classmethod
    def load(cls, db: Session, keep_unknown: bool = False) -> GenreFilter:
        return cls({row.tag: row.is_genre for row in db.query(GenreTag)}, keep_unknown)

    def is_genre(self, tag: str) -> bool:
        k = key(tag)
        if not k:
            return False
        if k in VOCABULARY:
            return True
        with self._lock:
            if k not in self._decisions:
                score = None if self._model_down else ask_model(tag)
                if score is None:  # not recorded: judged again next time
                    if not self._model_down:
                        self._model_down = True
                        logger.warning("genres: %s can't be asked; %s", settings.genre_model,
                                       "keeping unknown tags this run" if self._keep_unknown else "stopping")
                    if self._keep_unknown:
                        return True
                    raise GenreModelUnavailable(settings.genre_model)
                self._decisions[k] = score >= settings.genre_model_threshold
                self._new.append(GenreTag(tag=k, example=tag, is_genre=self._decisions[k], score=score,
                                          decided_by="model", decided_at=datetime.utcnow()))
                logger.info("genres: %r %s a genre (%.2f)", tag, "is" if self._decisions[k] else "isn't", score)
            return self._decisions[k]

    def keep(self, tags: list[str]) -> list[str]:
        return [t for t in tags if self.is_genre(t)]

    def save(self, db: Session) -> None:
        """Add the decisions made since loading (the caller commits)."""
        with self._lock:
            new, self._new = self._new, []
        for row in new:
            db.merge(row)
