from __future__ import annotations

import hashlib
import re

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.prompts import UNKNOWN_ANSWER
from app.main import create_app
from app.scrapers.darglobal import page_to_record, parse_sitemap, select_darglobal_urls
from app.services.intent import parse_intent
from app.scrapers.wasalt import parse_category_html
from app.utils.text import utc_now


WASALT_HTML = """
<html><head></head><body>
<script id="__NEXT_DATA__" type="application/json">
{"props":{"pageProps":{"searchResult":{"count":1,"properties":[{
  "id": 5893390,
  "floorSize": "1590",
  "contactDetails": {"phone": "0500000000", "whatsapp": "966500000000"},
  "leadContactInfo": {"phone": "0500000000"},
  "propertyInfo": {
    "title": "Apartment 1590 SQM with 2 Bedrooms",
    "city": "Riyadh",
    "district": "As-Saadah",
    "address": "As-Saadah, East Riyadh, Riyadh",
    "country": "Saudi Arabia",
    "salePrice": 704000,
    "currencyType": "SAR",
    "propertySubType": "Apartment",
    "propertyFor": "sale",
    "slug": "apartment-1590-sqm-with-2-bedrooms-5893390"
  },
  "attributes": [
    {"key": "noOfBedrooms", "value": 2},
    {"key": "noOfBathrooms", "value": 2},
    {"key": "builtUpArea", "value": "1590", "unit": "SQM"}
  ],
  "featureAmenities": [{"name": "Parking"}]
}]}}}}
</script>
</body></html>
"""

SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://darglobal.co.uk/</loc></url>
  <url><loc>https://darglobal.co.uk/blog/a-long-post</loc></url>
  <url><loc>https://darglobal.co.uk/press/new-jeddah-development</loc><lastmod>2026-11-16</lastmod></url>
  <url><loc>https://darglobal.co.uk/projects</loc></url>
  <url><loc>https://darglobal.co.uk/aida-trump-villas</loc></url>
  <url><loc>https://darglobal.co.uk/get-in-touch</loc></url>
</urlset>
"""


class HashEmbedder:
    dimension = 64

    def embed(self, texts: list[str]) -> np.ndarray:
        rows = []
        for text in texts:
            vector = np.zeros(self.dimension, dtype="float32")
            for token in re.findall(r"[a-z0-9]+", text.lower()):
                digest = hashlib.md5(token.encode()).hexdigest()
                vector[int(digest[:4], 16) % self.dimension] += 1.0
            norm = float(np.linalg.norm(vector) or 1.0)
            rows.append(vector / norm)
        if not rows:
            return np.zeros((0, self.dimension), dtype="float32")
        return np.vstack(rows)


class FakeLLM:
    def __init__(self) -> None:
        self.calls = 0
        self.configured = True
        self.resolved_model = "fake"

    def complete(self, messages: list[dict[str, str]]) -> str:
        self.calls += 1
        blob = "\n".join(message["content"] for message in messages)
        if "https://evil.example" in blob:
            return "See https://evil.example/fake for the price."
        if "AIDA" in blob:
            return "AIDA is a DarGlobal development."
        if "704000" in blob:
            answer = "The indexed asking price is 704000 SAR."
        else:
            answer = "Retrieved records were found."
        return answer + " See https://evil.example/fake"


@pytest.fixture
def app(tmp_path):
    settings = Settings(
        data_dir=str(tmp_path),
        admin_token="test-token",
        openrouter_api_key="",
        retrieval_threshold=0.05,
        retrieval_top_k=4,
        scraper_enabled=True,
        contact_email="",
    )
    llm = FakeLLM()
    application = create_app(settings=settings, embedder=HashEmbedder(), llm=llm)
    application.state.fake_llm = llm
    return application


@pytest.fixture
def client(app):
    return TestClient(app)


def test_wasalt_parser_keeps_public_fields_and_drops_contacts():
    records = parse_category_html(WASALT_HTML, "https://wasalt.sa/en/apartments-for-sale-in-riyadh", utc_now())
    assert len(records) == 1
    record = records[0]
    assert record.price == 704000
    assert record.city == "Riyadh"
    assert record.bedrooms == 2
    assert record.bathrooms == 2
    assert record.property_type == "Apartment"
    assert record.source_url.endswith("/property/sale/apartment-1590-sqm-with-2-bedrooms-5893390")
    assert "0500000000" not in record.content
    assert "whatsapp" not in record.content.lower()
    again = parse_category_html(WASALT_HTML, "https://wasalt.sa/en/apartments-for-sale-in-riyadh", utc_now())
    assert again[0].id == record.id


def test_wasalt_zero_price_is_null():
    html = WASALT_HTML.replace('"salePrice": 704000', '"salePrice": 0')
    record = parse_category_html(html, "https://wasalt.sa/en/apartments-for-sale-in-riyadh", utc_now())[0]
    assert record.price is None


def test_duplicate_upsert_does_not_create_a_second_row(app):
    records = parse_category_html(WASALT_HTML, "https://wasalt.sa/en/apartments-for-sale-in-riyadh", utc_now())
    repo = app.state.runtime.repository
    assert repo.upsert_record(records[0]) == "inserted"
    assert repo.upsert_record(records[0]) == "unchanged"
    assert repo.counts()["records"] == 1


def test_darglobal_sitemap_selection_skips_blog_and_contact_forms():
    pages = parse_sitemap(SITEMAP)
    selected = select_darglobal_urls(pages, limit=20)
    assert "https://darglobal.co.uk/blog/a-long-post" not in selected
    assert "https://darglobal.co.uk/get-in-touch" not in selected
    assert "https://darglobal.co.uk/press/new-jeddah-development" in selected
    assert "https://darglobal.co.uk/aida-trump-villas" in selected


def test_darglobal_page_record_extracts_location_without_inventing_price():
    record = page_to_record(
        "https://darglobal.co.uk/aida-trump-villas",
        {
            "h1": "Trump Cliff Villas",
            "title": "Trump Cliff Villas | DarGlobal",
            "description": "Villas in Muscat, Oman.",
            "text": "Trump Cliff Villas is a DarGlobal villa development in Muscat, Oman, with a golf course and hotel amenities. " * 3,
        },
        utc_now(),
    )
    assert record is not None
    assert record.category == "project"
    assert record.price is None
    assert record.country == "Oman"
    assert "Trump" in record.attributes["brands"]


def test_retrieval_filters_by_source(app):
    repo = app.state.runtime.repository
    now = utc_now()
    aida = page_to_record(
        "https://darglobal.co.uk/aida",
        {
            "h1": "AIDA",
            "title": "AIDA",
            "description": "",
            "text": "AIDA is a DarGlobal masterplanned development in Muscat Oman with villas and a golf community. " * 4,
        },
        now,
    )
    assert aida is not None
    listing = parse_category_html(WASALT_HTML, "https://wasalt.sa/en/apartments-for-sale-in-riyadh", now)[0]
    repo.upsert_record(aida)
    repo.upsert_record(listing)
    chunks = app.state.runtime.retrieval.rebuild()
    assert chunks == 2
    hits = app.state.runtime.retrieval.search("AIDA DarGlobal Muscat development", source="darglobal")
    assert hits
    assert {hit["source"] for hit in hits} == {"darglobal"}
    wasalt_hits = app.state.runtime.retrieval.search("Riyadh apartment bedrooms parking", source="wasalt")
    assert wasalt_hits
    assert {hit["source"] for hit in wasalt_hits} == {"wasalt"}
    assert all(hit["record_id"] != aida.id for hit in wasalt_hits)


def test_named_place_outside_the_index_is_refused(client, app):
    record = parse_category_html(WASALT_HTML, "https://wasalt.sa/en/apartments-for-sale-in-riyadh", utc_now())[0]
    client.app.state.runtime.repository.upsert_record(record)
    client.app.state.runtime.retrieval.rebuild()
    response = client.post("/api/chat", json={"message": "What is the rental yield in Antarctica?"})
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == UNKNOWN_ANSWER
    assert body["grounded"] is False
    assert body["properties"] == []
    assert app.state.fake_llm.calls == 0


def test_large_budget_without_rent_means_sale():
    sale = parse_intent("Show properties under SAR 1 million")
    assert sale.purpose == "sale"
    assert sale.max_price == 1_000_000
    rent = parse_intent("apartments for rent in Riyadh under SAR 20000")
    assert rent.purpose == "rent"
    assert rent.max_price == 20_000


def test_chat_unknown_question_does_not_call_the_model(client, app):
    response = client.post("/api/chat", json={"message": "What is the rental yield in Antarctica?"})
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == UNKNOWN_ANSWER
    assert body["grounded"] is False
    assert body["llm_used"] is False
    assert body["citations"] == []
    assert app.state.fake_llm.calls == 0


def test_chat_property_answer_cites_the_listing_url(client):
    from app.scrapers.wasalt import parse_category_html as parse_html

    record = parse_html(WASALT_HTML, "https://wasalt.sa/en/apartments-for-sale-in-riyadh", utc_now())[0]
    client.app.state.runtime.repository.upsert_record(record)
    response = client.post("/api/chat", json={"message": "Find apartments in Riyadh under SAR 1 million"})
    assert response.status_code == 200
    body = response.json()
    assert body["properties"]
    assert body["properties"][0]["price"] == 704000
    assert body["citations"][0]["source_url"] == record.source_url
    assert "evil.example" not in body["answer"]


def test_chat_strips_urls_that_are_not_in_the_context(client):
    record = page_to_record(
        "https://darglobal.co.uk/aida",
        {
            "h1": "AIDA",
            "title": "AIDA",
            "description": "",
            "text": "AIDA is a DarGlobal masterplanned development in Muscat Oman. " * 6,
        },
        utc_now(),
    )
    client.app.state.runtime.repository.upsert_record(record)
    client.app.state.runtime.retrieval.rebuild()
    response = client.post("/api/chat", json={"message": "Tell me about AIDA"})
    body = response.json()
    assert body["grounded"] is True
    assert "https://evil.example" not in body["answer"]
    assert body["citations"][0]["source_url"] == record.source_url


def test_follow_up_uses_the_previous_record(client):
    record = page_to_record(
        "https://darglobal.co.uk/aida",
        {
            "h1": "AIDA",
            "title": "AIDA",
            "description": "",
            "text": "AIDA is a DarGlobal masterplanned development in Muscat Oman with a golf course. " * 6,
        },
        utc_now(),
    )
    client.app.state.runtime.repository.upsert_record(record)
    client.app.state.runtime.retrieval.rebuild()
    first = client.post("/api/chat", json={"message": "Tell me about AIDA"}).json()
    second = client.post(
        "/api/chat",
        json={"message": "What is its location?", "session_id": first["session_id"]},
    ).json()
    assert second["grounded"] is True
    assert second["citations"][0]["source_url"] == record.source_url


def test_admin_scrape_requires_token(client):
    denied = client.post("/api/scrape/run")
    assert denied.status_code == 401
    client.app.state.runtime.jobs.start = lambda target: True
    allowed = client.post("/api/scrape/run", headers={"X-Admin-Token": "test-token"})
    assert allowed.status_code == 200
    assert allowed.json()["status"] == "started"


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
