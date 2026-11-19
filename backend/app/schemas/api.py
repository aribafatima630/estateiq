from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Citation(BaseModel):
    title: str
    source: str
    source_url: str
    category: str


class PropertyCard(BaseModel):
    id: str
    title: str
    source: str
    location: str | None = None
    city: str | None = None
    price: float | None = None
    currency: str | None = None
    property_type: str | None = None
    purpose: str | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    area_sqm: float | None = None
    source_url: str


class ProjectCard(BaseModel):
    id: str
    title: str
    location: str | None = None
    property_type: str | None = None
    summary: str
    source_url: str
    brands: list[str] = Field(default_factory=list)


class ComparisonRow(BaseModel):
    label: str
    values: list[str]


class ComparisonTable(BaseModel):
    columns: list[str]
    rows: list[ComparisonRow]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None
    source_filter: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    grounded: bool
    llm_used: bool
    citations: list[Citation] = Field(default_factory=list)
    properties: list[PropertyCard] = Field(default_factory=list)
    projects: list[ProjectCard] = Field(default_factory=list)
    comparison: ComparisonTable | None = None


class HealthResponse(BaseModel):
    status: str
    database: bool
    index_ready: bool
    records: int
    llm_configured: bool
    scraper_enabled: bool


class StatsResponse(BaseModel):
    records: int
    chunks: int
    by_source: dict[str, int]
    by_category: dict[str, int]
    index_ready: bool
    llm_configured: bool
    resolved_model: str | None = None
    last_scrape: dict[str, Any] | None = None
