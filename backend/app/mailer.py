"""Sending an email through Resend: the one place that posts to its API. The weekly Alerts (app/alerts.py) and the
maintainer's emails about the ingest (app/notifications.py) both send through here."""
from __future__ import annotations

import httpx

RESEND_URL = "https://api.resend.com/emails"


class SendError(RuntimeError):
    pass


def post_email(*, api_key: str, sender: str, to: str, subject: str, html: str, text: str,
               headers: dict[str, str] | None = None, idempotency_key: str | None = None) -> None:
    """Send one email with an HTML and a plain-text version; raises when Resend refuses it.

    With an `idempotency_key`, Resend drops a repeat of the same email sent with the same key within 24 hours, and
    refuses (409) a different email sent with it. `headers` are the email's own, such as List-Unsubscribe.
    """
    request_headers = {"Authorization": f"Bearer {api_key}"}
    if idempotency_key:
        request_headers["Idempotency-Key"] = idempotency_key
    body = {"from": sender, "to": [to], "subject": subject, "html": html, "text": text}
    if headers:
        body["headers"] = headers
    response = httpx.post(RESEND_URL, json=body, headers=request_headers, timeout=30.0)
    response.raise_for_status()
