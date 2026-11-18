"""A Band's photo on Wikimedia Commons, found through its MusicBrainz links: the "wikidata" relationship names the
artist's Wikidata item, whose image (property P18) is a Commons file. The Commons image info API gives the file's
thumbnail and its credit (author, licence, licence URL, file page), which the site must show (most Commons photos
are CC BY or CC BY-SA).

Only links on the matched MusicBrainz artist are followed, never a search by name, so a namesake's photo can't be
picked up. Any failure (missing item, no image, HTTP error, timeout) means no photo; this never raises.
"""
from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass

import httpx

from app.ingestion.images import wikimedia_file_title
from app.ingestion.service_health import note_failure

logger = logging.getLogger(__name__)

_USER_AGENT = "the-list/0.1 (https://github.com/jsturgis/the_list)"  # Wikimedia rejects requests without one
_ENTITY = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
_COMMONS_API = "https://commons.wikimedia.org/w/api.php"
_THUMB_WIDTH = 800  # Commons rounds up to its standard widths; the download step resizes anyway
_QID = re.compile(r"wikidata\.org/(?:wiki|entity)/(Q\d+)$")
_TAG = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class CommonsPhoto:
    url: str        # the thumbnail to download
    credit: dict    # author, license, license_url, source_url (the Commons file page)


def _wikidata_id(links: list[dict]) -> str | None:
    for link in links or []:
        if link.get("type") == "wikidata" and (m := _QID.search(link.get("url", "").rstrip("/"))):
            return m.group(1)
    return None


def _image_file(claims: list[dict]) -> str | None:
    """The image Wikidata ranks first: a preferred claim, else the first normal one. Claims without a value
    ("no value", "unknown value") and deprecated ones don't count."""
    usable = [c for c in claims if c.get("rank", "normal") != "deprecated"
              and c.get("mainsnak", {}).get("snaktype", "value") == "value"
              and c.get("mainsnak", {}).get("datavalue", {}).get("value")]
    best = next((c for c in usable if c.get("rank") == "preferred"), usable[0] if usable else None)
    return best["mainsnak"]["datavalue"]["value"] if best else None


def _plain(markup: str | None) -> str | None:
    """Commons metadata as plain text: tags removed, entities decoded, whitespace collapsed."""
    if not markup:
        return None
    return " ".join(html.unescape(_TAG.sub(" ", markup)).split()) or None


def _credit(info: dict) -> dict:
    """A Commons file's credit, from its image info: author, licence, licence URL and its file page."""
    meta = info.get("extmetadata", {})
    return {
        "source": "Wikimedia Commons",
        "author": _plain(meta.get("Artist", {}).get("value")),
        "license": _plain(meta.get("LicenseShortName", {}).get("value")),
        "license_url": (meta.get("LicenseUrl", {}).get("value") or None),
        "source_url": info["descriptionurl"],
    }


def commons_credit(url: str, client: httpx.Client | None = None) -> dict | None:
    """The credit of the Commons file at `url` (an upload.wikimedia.org original or thumbnail), for a photo known
    by its URL rather than found through Wikidata (a Venue's). None when `url` isn't a Commons file, or the file
    can't be looked up right now; this never raises."""
    title = wikimedia_file_title(url)
    if title is None:
        return None
    own_client = client is None
    client = client or httpx.Client(timeout=20, follow_redirects=True, headers={"User-Agent": _USER_AGENT})
    try:
        pages = client.get(_COMMONS_API, params={
            "action": "query", "format": "json", "prop": "imageinfo", "iiprop": "url|extmetadata", "titles": title,
        }).raise_for_status().json()["query"]["pages"]
        return _credit(next(iter(pages.values()))["imageinfo"][0])
    except Exception:
        logger.info("wikimedia: no credit for %s", url, exc_info=True)
        return None
    finally:
        if own_client:
            client.close()


def commons_photo(links: list[dict], client: httpx.Client | None = None) -> CommonsPhoto | None:
    """The Band's Commons photo and its credit, from its MusicBrainz links; None when there isn't one."""
    qid = _wikidata_id(links)
    if qid is None:
        return None
    own_client = client is None
    client = client or httpx.Client(timeout=20, follow_redirects=True, headers={"User-Agent": _USER_AGENT})
    try:
        entity = client.get(_ENTITY.format(qid=qid)).raise_for_status().json()["entities"]
        file_name = _image_file(next(iter(entity.values())).get("claims", {}).get("P18") or [])
        if file_name is None:
            return None
        pages = client.get(_COMMONS_API, params={
            "action": "query", "format": "json", "prop": "imageinfo", "iiprop": "url|extmetadata",
            "iiurlwidth": _THUMB_WIDTH, "titles": f"File:{file_name}",
        }).raise_for_status().json()["query"]["pages"]
        info = next(iter(pages.values()))["imageinfo"][0]
        url = (info.get("thumburl") or info["url"]).split("?")[0]  # drop Commons' tracking parameters
        return CommonsPhoto(url, _credit(info))
    except Exception as exc:
        note_failure("Wikimedia Commons", exc)
        logger.info("wikimedia: no Commons photo for %s", qid, exc_info=True)
        return None
    finally:
        if own_client:
            client.close()
