from __future__ import annotations

import re


def chunk_text(text: str, size: int = 900, overlap: int = 140) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n{2,}", text) if part.strip()]
    if not paragraphs:
        compact = " ".join(text.split())
        return [compact] if compact else []
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > size:
            if current:
                chunks.append(current.strip())
                current = ""
            start = 0
            while start < len(paragraph):
                chunks.append(paragraph[start : start + size].strip())
                start += size - overlap
            continue
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= size:
            current = candidate
        else:
            if current:
                chunks.append(current.strip())
            current = paragraph
    if current:
        chunks.append(current.strip())
    return [chunk for chunk in chunks if chunk]


def chunks_for_record(record: dict) -> list[dict]:
    text = (record.get("content") or "").strip()
    if not text:
        return []
    if record.get("category") == "property" or len(text) <= 1100:
        pieces = [text]
    else:
        pieces = chunk_text(text)
    chunks = []
    for index, piece in enumerate(pieces):
        chunks.append(
            {
                "id": f"{record['id']}:{index}",
                "record_id": record["id"],
                "text": piece,
                "source": record["source"],
                "title": record["title"],
                "category": record["category"],
                "location": record.get("location"),
                "city": record.get("city"),
                "property_type": record.get("property_type"),
                "source_url": record["source_url"],
                "price": record.get("price"),
                "bedrooms": record.get("bedrooms"),
                "purpose": record.get("purpose"),
            }
        )
    return chunks
