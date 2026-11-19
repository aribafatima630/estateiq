from __future__ import annotations

import re
import uuid

from app.core.prompts import LLM_UNAVAILABLE, SYSTEM_PROMPT, UNKNOWN_ANSWER
from app.database.repository import Repository
from app.rag.retrieval import RetrievalService
from app.schemas.api import (
    ChatResponse,
    Citation,
    ComparisonRow,
    ComparisonTable,
    ProjectCard,
    PropertyCard,
)
from app.services.intent import CITIES, QueryIntent, parse_intent
from app.services.llm import LLMUnavailable, OpenRouterClient
from app.utils.text import utc_now

URL_RE = re.compile(r"https?://\S+")
PLACE_RE = re.compile(r"\b(?:in|at|near|around)\s+([a-z][a-z'’-]{3,}(?:\s+[a-z][a-z'’-]{3,})?)\b", re.I)
KNOWN_PLACES = {needle for needle, _label in CITIES} | {label.lower() for _needle, label in CITIES}
PLACE_STOPWORDS = {
    "general",
    "total",
    "particular",
    "question",
    "index",
    "dataset",
    "indexed",
    "present",
    "available",
    "information",
    "data",
    "source",
    "sources",
    "market",
    "markets",
    "area",
    "areas",
    "city",
    "cities",
    "country",
    "countries",
    "region",
    "regions",
    "project",
    "projects",
    "development",
    "developments",
    "property",
    "properties",
    "listing",
    "listings",
    "sale",
    "rent",
    "saudi",
    "estate",
    "real",
    "this",
    "that",
    "these",
    "those",
    "both",
    "which",
    "what",
}


class ChatService:
    def __init__(self, repository: Repository, retrieval: RetrievalService, llm: OpenRouterClient):
        self.repository = repository
        self.retrieval = retrieval
        self.llm = llm

    def answer(self, message: str, session_id: str | None, source_filter: str | None) -> ChatResponse:
        source_filter = _normalise_source(source_filter)
        now = utc_now()
        session = self.repository.get_session(session_id) if session_id else None
        created = False
        if session is None:
            session_id = uuid.uuid4().hex
            title = message.strip()[:80]
            self.repository.create_session(session_id, title, source_filter, now)
            session = self.repository.get_session(session_id)
            created = True
        elif source_filter != session.get("source_filter"):
            self.repository.update_session(
                session_id,
                source_filter=source_filter,
                last_record_ids=session.get("last_record_ids") or [],
                now=now,
            )
            session["source_filter"] = source_filter
        assert session is not None and session_id is not None

        intent = parse_intent(message)
        if source_filter in {"darglobal", "wasalt"}:
            intent.source = source_filter
        if intent.catalog:
            return self._catalog_answer(session_id, message, intent, now)

        records: list[dict] = []
        comparison: ComparisonTable | None = None
        if intent.anaphoric:
            records = self._follow_up(session, intent)
        if intent.comparison and not records:
            comparison, records = self._comparison()
        elif intent.latest and not records:
            news_source = intent.source
            if news_source is None and "darglobal" in message.lower():
                news_source = "darglobal"
            records = self.repository.latest_news(news_source, limit=6)
        elif intent.countries and not records:
            records = self._country_records(intent)
        elif intent.title_query and not records:
            records = self.repository.list_records(
                source=intent.source,
                title_query=intent.title_query,
                limit=6,
            )
        elif intent.structured and not records:
            records = self._structured_records(intent)
        elif intent.list_projects and not records:
            records = self.repository.list_records(
                source=intent.source or "darglobal",
                category="project",
                city=intent.city,
                limit=8,
            )

        vector_hits = []
        # Filtered database hits are already the answer. Skip the embedding search so those
        # questions stay fast and unfiltered vector matches cannot dilute them.
        # A specific title that is not in the database must not be backfilled with nearby hits.
        if not records and not comparison and not intent.title_query:
            try:
                vector_hits = self.retrieval.search(
                    message,
                    source=intent.source,
                    location=intent.city,
                    property_type=intent.property_type if intent.source == "darglobal" else None,
                )
            except Exception:
                vector_hits = []
        merged = _merge_records(records, vector_hits, self.repository)
        merged = _require_named_place(message, merged)
        merged = _drop_unsupported_claims(message, merged)
        self.repository.add_message(uuid.uuid4().hex, session_id, "user", message.strip(), None, now)
        if not merged:
            response = ChatResponse(
                session_id=session_id,
                answer=UNKNOWN_ANSWER,
                grounded=False,
                llm_used=False,
            )
            self._store_assistant(session_id, response, [])
            return response

        context_records = [record for record in merged if record.get("source_url")]
        llm_used = False
        try:
            answer = self.llm.complete(self._messages(session_id, context_records, comparison))
            llm_used = True
            if UNKNOWN_ANSWER in answer and not _browse_intent(intent):
                response = ChatResponse(
                    session_id=session_id,
                    answer=UNKNOWN_ANSWER,
                    grounded=False,
                    llm_used=False,
                )
                self._store_assistant(session_id, response, [])
                return response
            if UNKNOWN_ANSWER in answer:
                answer = _extractive_summary(context_records)
                llm_used = False
        except LLMUnavailable:
            answer = LLM_UNAVAILABLE + "\n\n" + _extractive_summary(context_records)
        allowed_urls = {record["source_url"] for record in context_records}
        answer = URL_RE.sub(lambda match: match.group(0) if match.group(0).rstrip(").,") in allowed_urls else "", answer)
        answer = re.sub(r"[ \t]{2,}", " ", answer).strip()
        response = ChatResponse(
            session_id=session_id,
            answer=answer,
            grounded=True,
            llm_used=llm_used,
            citations=_citations(context_records),
            properties=_property_cards(context_records),
            projects=_project_cards(context_records),
            comparison=comparison,
        )
        self._store_assistant(session_id, response, [record["id"] for record in context_records if record.get("id")])
        if created:
            return response
        return response

    def _catalog_answer(self, session_id: str, message: str, intent: QueryIntent, now: str) -> ChatResponse:
        self.repository.add_message(uuid.uuid4().hex, session_id, "user", message.strip(), None, now)
        counts = self.repository.property_type_counts(intent.source)
        if not counts:
            response = ChatResponse(
                session_id=session_id,
                answer=UNKNOWN_ANSWER,
                grounded=False,
                llm_used=False,
            )
        else:
            lines = [
                f"{row['source']} / {row['property_type']}: {row['n']} indexed records" for row in counts
            ]
            response = ChatResponse(
                session_id=session_id,
                answer="Property types present in the indexed dataset:\n" + "\n".join(lines),
                grounded=True,
                llm_used=False,
            )
        self._store_assistant(session_id, response, [])
        return response

    def _store_assistant(self, session_id: str, response: ChatResponse, record_ids: list[str]) -> None:
        now = utc_now()
        payload = response.model_dump()
        self.repository.add_message(uuid.uuid4().hex, session_id, "assistant", response.answer, payload, now)
        session = self.repository.get_session(session_id)
        kept_ids = record_ids[:8] or (session.get("last_record_ids") if session else [])
        self.repository.update_session(
            session_id,
            source_filter=session.get("source_filter") if session else None,
            last_record_ids=kept_ids,
            now=now,
        )

    def _messages(self, session_id: str, records: list[dict], comparison: ComparisonTable | None) -> list[dict[str, str]]:
        history = self.repository.list_messages(session_id)[-6:]
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for item in history:
            if item["role"] in {"user", "assistant"}:
                messages.append({"role": item["role"], "content": item["content"][:800]})
        messages.append({"role": "user", "content": _context_message(records, comparison)})
        return messages

    def _follow_up(self, session: dict, intent: QueryIntent) -> list[dict]:
        previous_ids = session.get("last_record_ids") or []
        previous = self.repository.get_records(previous_ids)
        if not previous:
            return []
        if intent.ordinal is not None:
            index = intent.ordinal if intent.ordinal >= 0 else len(previous) - 1
            if index < 0 or index >= len(previous):
                return []
            selected = previous[index]
            if intent.similar:
                return self._similar(selected)
            return [selected]
        if intent.similar:
            return self._similar(previous[0])
        return [previous[0]]

    def _similar(self, record: dict) -> list[dict]:
        rows = self.repository.list_records(
            source=record.get("source"),
            category=record.get("category"),
            city=record.get("city"),
            property_type=record.get("property_type"),
            purpose=record.get("purpose"),
            limit=6,
        )
        return [row for row in rows if row["id"] != record["id"]][:5]

    def _structured_records(self, intent: QueryIntent) -> list[dict]:
        budget = intent.min_price is not None or intent.max_price is not None
        listing_query = budget or intent.bedrooms is not None or intent.purpose == "rent"
        if intent.source == "darglobal":
            return self.repository.list_records(
                source="darglobal",
                category="project",
                city=intent.city,
                property_type=intent.property_type,
                limit=8,
            )
        properties = self.repository.list_records(
            source="wasalt" if listing_query or intent.source == "wasalt" else None,
            category="property",
            city=intent.city,
            property_type=intent.property_type,
            purpose=intent.purpose,
            bedrooms=intent.bedrooms,
            min_price=intent.min_price,
            max_price=intent.max_price,
            currency=intent.currency if budget else None,
            limit=8,
        )
        if listing_query:
            return properties
        projects = self.repository.list_records(
            source="darglobal",
            category="project",
            city=intent.city,
            property_type=intent.property_type,
            limit=4,
        )
        if intent.source == "darglobal":
            return projects
        if intent.source == "wasalt":
            return properties
        return properties + projects

    def _country_records(self, intent: QueryIntent) -> list[dict]:
        source = intent.source or "darglobal"
        company = self.repository.list_records(source=source, category="company", limit=2)
        projects = self.repository.list_records(source=source, category="project", limit=10)
        return company + projects

    def _comparison(self) -> tuple[ComparisonTable, list[dict]]:
        dg_company = self.repository.list_records(source="darglobal", category="company", limit=1)
        wa_company = self.repository.list_records(source="wasalt", category="company", limit=1)
        dg_projects = self.repository.list_records(source="darglobal", category="project", limit=4)
        wa_properties = self.repository.list_records(source="wasalt", category="property", limit=4)
        counts = self.repository.counts()
        rows = [
            ComparisonRow(
                label="Indexed records",
                values=[
                    str(counts["by_source"].get("darglobal", 0)),
                    str(counts["by_source"].get("wasalt", 0)),
                ],
            ),
            ComparisonRow(
                label="What the indexed pages describe",
                values=[
                    _opening(dg_company),
                    _opening(wa_company),
                ],
            ),
            ComparisonRow(
                label="Locations in the index",
                values=[
                    "; ".join(self.repository.distinct_places("darglobal", "project")[:6]) or "None indexed",
                    "; ".join(self.repository.distinct_places("wasalt", "property")[:6]) or "None indexed",
                ],
            ),
            ComparisonRow(
                label="Records with a published price",
                values=[
                    str(self.repository.priced_count("darglobal")),
                    str(self.repository.priced_count("wasalt")),
                ],
            ),
            ComparisonRow(
                label="Examples",
                values=[
                    "; ".join(row["title"] for row in dg_projects[:3]) or "None indexed",
                    "; ".join(row["title"] for row in wa_properties[:3]) or "None indexed",
                ],
            ),
        ]
        table = ComparisonTable(columns=["DarGlobal", "Wasalt"], rows=rows)
        return table, dg_company + dg_projects + wa_company + wa_properties


def _browse_intent(intent: QueryIntent) -> bool:
    return bool(
        intent.structured
        or intent.list_projects
        or intent.comparison
        or intent.countries
        or intent.latest
        or intent.catalog
        or intent.anaphoric
    )


def _drop_unsupported_claims(message: str, records: list[dict]) -> list[dict]:
    """A guaranteed figure can be shown only when a retrieved page actually says so."""
    if not re.search(r"\bguaranteed\b", message, re.I):
        return records
    kept = []
    for record in records:
        blob = f"{record.get('title') or ''} {record.get('content') or ''}".lower()
        if "guaranteed" in blob:
            kept.append(record)
    return kept


def _normalise_source(value: str | None) -> str | None:
    if not value:
        return None
    lowered = value.strip().lower()
    if lowered in {"darglobal", "dar global", "dar"}:
        return "darglobal"
    if lowered in {"wasalt"}:
        return "wasalt"
    return None


def _require_named_place(message: str, records: list[dict]) -> list[dict]:
    """Drop records that do not mention a place the question names."""
    match = PLACE_RE.search(message)
    if not match or not records:
        return records
    place = " ".join(match.group(1).lower().split())
    tokens = place.split()
    if (
        place in KNOWN_PLACES
        or place in PLACE_STOPWORDS
        or any(token in KNOWN_PLACES or token in PLACE_STOPWORDS for token in tokens)
    ):
        return records
    kept = []
    for record in records:
        blob = " ".join(
            str(record.get(key) or "")
            for key in ("title", "location", "city", "country", "content")
        ).lower()
        if place in blob:
            kept.append(record)
    return kept


def _merge_records(primary: list[dict], hits: list[dict], repository: Repository) -> list[dict]:
    merged: list[dict] = []
    seen: set[str] = set()
    for record in primary:
        record_id = record.get("id")
        if record_id and record_id not in seen:
            seen.add(record_id)
            merged.append(record)
    missing_ids = []
    for hit in hits:
        record_id = hit.get("record_id")
        if record_id and record_id not in seen:
            missing_ids.append(record_id)
            seen.add(record_id)
    for record in repository.get_records(missing_ids):
        merged.append(record)
    return merged[:8]


def _context_message(records: list[dict], comparison: ComparisonTable | None) -> str:
    blocks = ["Verified context:"]
    for index, record in enumerate(records, start=1):
        details = [
            f"[{index}] {record.get('title')}",
            f"Source: {record.get('source')}",
            f"Category: {record.get('category')}",
            f"URL: {record.get('source_url')}",
        ]
        if record.get("location"):
            details.append(f"Location: {record['location']}")
        if record.get("price") is not None:
            details.append(f"Price: {record['price']} {record.get('currency') or ''}".strip())
        if record.get("bedrooms") is not None:
            details.append(f"Bedrooms: {record['bedrooms']}")
        if record.get("bathrooms") is not None:
            details.append(f"Bathrooms: {record['bathrooms']}")
        if record.get("area_sqm") is not None:
            details.append(f"Area SQM: {record['area_sqm']}")
        if record.get("property_type"):
            details.append(f"Type: {record['property_type']}")
        details.append(record.get("content") or "")
        blocks.append("\n".join(details))
    locations = []
    for record in records:
        if record.get("location") and record["location"] not in locations:
            locations.append(record["location"])
    if locations:
        blocks.append("Locations named on the records above: " + "; ".join(locations[:12]) + ".")
    if comparison:
        blocks.append("A comparison table built only from these indexed records will be shown beside your answer.")
    blocks.append("Answer the user's latest question using only this context.")
    return "\n\n".join(blocks)


def _extractive_summary(records: list[dict]) -> str:
    lines = []
    for record in records[:6]:
        bits = [f"{record.get('source')}: {record.get('title')}"]
        if record.get("location"):
            bits.append(f"Location: {record['location']}")
        if record.get("price") is not None:
            bits.append(f"Price: {record['price']} {record.get('currency') or ''}".strip())
        if record.get("bedrooms") is not None:
            bits.append(f"Bedrooms: {record['bedrooms']}")
        lines.append(". ".join(bits) + ".")
    return "\n".join(lines)


def _citations(records: list[dict]) -> list[Citation]:
    citations = []
    seen = set()
    for record in records:
        url = record.get("source_url")
        if not url or url in seen:
            continue
        seen.add(url)
        citations.append(
            Citation(
                title=record.get("title") or url,
                source=record.get("source") or "",
                source_url=url,
                category=record.get("category") or "",
            )
        )
    return citations


def _property_cards(records: list[dict]) -> list[PropertyCard]:
    cards = []
    for record in records:
        if record.get("category") != "property":
            continue
        cards.append(
            PropertyCard(
                id=record["id"],
                title=record["title"],
                source=record["source"],
                location=record.get("location"),
                city=record.get("city"),
                price=record.get("price"),
                currency=record.get("currency"),
                property_type=record.get("property_type"),
                purpose=record.get("purpose"),
                bedrooms=record.get("bedrooms"),
                bathrooms=record.get("bathrooms"),
                area_sqm=record.get("area_sqm"),
                source_url=record["source_url"],
            )
        )
    return cards[:6]


def _project_cards(records: list[dict]) -> list[ProjectCard]:
    cards = []
    for record in records:
        if record.get("category") != "project":
            continue
        summary = " ".join((record.get("content") or "").split())[:280]
        brands = record.get("attributes", {}).get("brands") or []
        if not isinstance(brands, list):
            brands = []
        cards.append(
            ProjectCard(
                id=record["id"],
                title=record["title"],
                location=record.get("location"),
                property_type=record.get("property_type"),
                summary=summary,
                source_url=record["source_url"],
                brands=[str(brand) for brand in brands],
            )
        )
    return cards[:6]


def _opening(records: list[dict]) -> str:
    if not records:
        return "No description indexed"
    sentence = re.split(r"(?<=\.)\s", records[0].get("content") or "")[0]
    return sentence[:220] or "No description indexed"
