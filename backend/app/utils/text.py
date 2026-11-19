from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

PHONE_IN_HREF = re.compile(r"^(tel:|mailto:|https?://(wa\.me|api\.whatsapp\.com))", re.I)
WHITESPACE = re.compile(r"[ \t]+\n")
BLANK_LINES = re.compile(r"\n{3,}")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_id(source: str, key: str) -> str:
    digest = hashlib.sha256(f"{source}:{key}".encode("utf-8")).hexdigest()
    return digest[:24]


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


def clean_text(value: str | None, limit: int = 12000) -> str:
    if not value:
        return ""
    text = value.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\xa0", " ")
    text = WHITESPACE.sub("\n", text)
    text = BLANK_LINES.sub("\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()[:limit]


def parse_number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if number > 0 else None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return None
    number = float(match.group(0))
    return number if number > 0 else None


def parse_int(value: object) -> int | None:
    number = parse_number(value)
    if number is None:
        return None
    return int(number)


def same_host(url: str, host: str) -> bool:
    return urlsplit(url).netloc.lower().endswith(host.lower())
