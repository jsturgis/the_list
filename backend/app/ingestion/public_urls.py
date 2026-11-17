"""URLs that came from somewhere we don't control (an LLM reading a Venue's web page), made safe to store, show and
fetch: http(s) only, and never a host on this machine or a private network.

- `public_url` checks a URL as text (scheme, and a host that isn't localhost or a private/reserved IP), resolving
  a relative one against the page it was found on. It's what decides whether a link is stored at all.
- `guarded_client` is an httpx.Client that also checks every request it makes, redirects included, and refuses
  any whose host resolves to a non-public address -- so a link that looks public but points (or redirects) at
  e.g. 169.254.169.254 or the runner's own Ollama is never fetched.
- `same_site` compares two URLs' sites (the last two labels of the host: "www.gamh.com" and "gamh.com" match),
  for links that should be on the Venue's own site.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

import httpx

_LOCAL_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home.arpa")


def _is_public_ip(host: str) -> bool | None:
    """True/False for an IP address literal; None for a hostname."""
    try:
        return ipaddress.ip_address(host.strip("[]")).is_global
    except ValueError:
        return None


def public_url(url: str | None, base: str | None = None) -> str | None:
    """`url` (resolved against `base` when relative) if it's an http(s) URL on a public host, else None."""
    if not url:
        return None
    url = urljoin(base, url.strip()) if base else url.strip()
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    host = (parts.hostname or "").lower().rstrip(".")
    if parts.scheme not in ("http", "https") or not host or "." not in host and _is_public_ip(host) is None:
        return None
    if host == "localhost" or host.endswith(_LOCAL_SUFFIXES):
        return None
    return url if _is_public_ip(host) is not False else None


def resolves_publicly(host: str) -> bool:
    """False if `host` resolves to any non-public address. A host that doesn't resolve at all counts as public:
    the request fails by itself."""
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError):
        return True
    return all(ipaddress.ip_address(info[4][0].split("%")[0]).is_global for info in infos)


def _guard(request: httpx.Request) -> None:
    url = str(request.url)
    if public_url(url) is None or not resolves_publicly(request.url.host):
        raise httpx.ConnectError(f"refused a non-public URL: {url}", request=request)


def guarded_client(**kwargs) -> httpx.Client:
    """An httpx.Client that refuses any request (redirects included) to a non-public URL, raising ConnectError."""
    return httpx.Client(event_hooks={"request": [_guard]}, **kwargs)


def site(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    return ".".join(host.split(".")[-2:])


def same_site(url: str, *others: str | None) -> bool:
    """Whether `url` is on the same site as any of `others`."""
    return any(other and site(url) == site(other) for other in others)
