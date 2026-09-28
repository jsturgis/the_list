"""Gmail API client — fetches Steve List emails from the watched inbox."""
from __future__ import annotations

import base64
import os
import quopri

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from app.config import settings

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def get_gmail_service():
    creds = None
    if os.path.exists(settings.gmail_token_path):
        creds = Credentials.from_authorized_user_file(settings.gmail_token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                settings.gmail_credentials_path, SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open(settings.gmail_token_path, "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def _decode_part(part: dict) -> str | None:
    """Base64url-decode a message part's body, applying QP decoding when needed."""
    data = part.get("body", {}).get("data", "")
    if not data:
        return None
    raw = base64.urlsafe_b64decode(data + "==")
    headers = {h["name"].lower(): h["value"].lower() for h in part.get("headers", [])}
    if headers.get("content-transfer-encoding") == "quoted-printable":
        raw = quopri.decodestring(raw)
    return raw.decode("utf-8", errors="replace")


def _find_text_plain(payload: dict) -> str | None:
    """Recursively find and decode the first text/plain part."""
    if payload.get("mimeType") == "text/plain":
        return _decode_part(payload)
    for part in payload.get("parts", []):
        result = _find_text_plain(part)
        if result:
            return result
    return None


def fetch_latest_list_email() -> str | None:
    """Return the plain-text body of the most recent Steve List email, or None."""
    service = get_gmail_service()
    results = service.users().messages().list(
        userId="me",
        q=f"from:{settings.gmail_watch_email}",
        maxResults=1,
    ).execute()

    messages = results.get("messages", [])
    if not messages:
        return None

    msg = service.users().messages().get(
        userId="me",
        id=messages[0]["id"],
        format="full",
    ).execute()

    return _find_text_plain(msg.get("payload", {}))
