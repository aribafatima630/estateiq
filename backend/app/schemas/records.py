from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Source = Literal["darglobal", "wasalt"]
Category = Literal["project", "property", "news", "company"]


class Record(BaseModel):
    id: str
    source: Source
    title: str
    content: str
    category: Category
    location: str | None = None
    price: float | None = None
    property_type: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    source_url: str
    scraped_at: str
    city: str | None = None
    country: str | None = None
    currency: str | None = None
    purpose: str | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    area_sqm: float | None = None
    published_at: str | None = None
    content_hash: str = ""
