from __future__ import annotations

import re
from dataclasses import dataclass


CITIES = (
    ("al khobar", "Al Khobar"),
    ("khobar", "Al Khobar"),
    ("riyadh", "Riyadh"),
    ("jeddah", "Jeddah"),
    ("makkah", "Makkah"),
    ("mecca", "Makkah"),
    ("madinah", "Madinah"),
    ("medina", "Madinah"),
    ("dammam", "Dammam"),
    ("wadi safar", "Wadi Safar"),
    ("dubai", "Dubai"),
    ("abu dhabi", "Abu Dhabi"),
    ("ras al khaimah", "Ras Al Khaimah"),
    ("muscat", "Muscat"),
    ("oman", "Oman"),
    ("doha", "Doha"),
    ("simaisma", "Simaisma"),
    ("qatar", "Qatar"),
    ("london", "London"),
    ("united kingdom", "United Kingdom"),
    ("spain", "Spain"),
    ("saudi arabia", "Saudi Arabia"),
    ("united arab emirates", "United Arab Emirates"),
)
PROPERTY_TYPES = (
    ("apartment", r"\bapartments?\b|\bflats?\b"),
    ("villa", r"\bvillas?\b"),
    ("land", r"\blands?\b|\bplots?\b"),
    ("mansion", r"\bmansions?\b"),
    ("hotel", r"\bhotels?\b"),
)
WORD_NUMBERS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
}
ORDINALS = {
    "first": 0,
    "1st": 0,
    "second": 1,
    "2nd": 1,
    "third": 2,
    "3rd": 2,
    "fourth": 3,
    "4th": 3,
    "fifth": 4,
    "5th": 4,
    "last": -1,
}


@dataclass
class QueryIntent:
    source: str | None = None
    city: str | None = None
    property_type: str | None = None
    purpose: str | None = None
    bedrooms: int | None = None
    min_price: float | None = None
    max_price: float | None = None
    currency: str | None = None
    comparison: bool = False
    latest: bool = False
    countries: bool = False
    list_projects: bool = False
    ordinal: int | None = None
    anaphoric: bool = False
    similar: bool = False
    title_query: str | None = None

    @property
    def structured(self) -> bool:
        return any(
            value is not None
            for value in (
                self.city,
                self.property_type,
                self.purpose,
                self.bedrooms,
                self.min_price,
                self.max_price,
            )
        )


def _amount(number: str, unit: str | None) -> float:
    value = float(number.replace(",", ""))
    unit = (unit or "").lower()
    if unit in {"million", "m"}:
        return value * 1_000_000
    if unit == "k":
        return value * 1_000
    return value


def parse_intent(message: str) -> QueryIntent:
    text = " ".join(message.lower().split())
    intent = QueryIntent()
    if re.search(r"\bdar\s*global\b|\bdarglobal\b", text):
        intent.source = "darglobal"
    elif re.search(r"\bwasalt\b", text):
        intent.source = "wasalt"
    if re.search(r"\b(compare|comparison|differences?|versus|vs)\b", text) or "both datasets" in text or "both sources" in text:
        intent.comparison = True
    if re.search(r"\b(latest|recent|announcement|news|press)\b", text):
        intent.latest = True
    if re.search(r"\b(which countries|what countries|where does|markets|operate)\b", text):
        intent.countries = True
    if re.search(r"\b(projects|developments|portfolio)\b", text) and intent.source != "wasalt":
        intent.list_projects = True
    if re.search(r"\b(for rent|rental|to rent)\b", text):
        intent.purpose = "rent"
    elif re.search(r"\b(for sale|to buy|buy)\b", text):
        intent.purpose = "sale"
    for needle, label in CITIES:
        if re.search(rf"\b{re.escape(needle)}\b", text):
            intent.city = label
            break
    for label, pattern in PROPERTY_TYPES:
        if re.search(pattern, text):
            intent.property_type = label
            break
    bedroom = re.search(r"\b(\d+|one|two|three|four|five|six)\s*[- ]?bed(?:room)?s?\b", text)
    if bedroom:
        token = bedroom.group(1)
        intent.bedrooms = WORD_NUMBERS.get(token, int(token) if token.isdigit() else None)
    amount = r"(?:(?:sar|sr|riyals?)\s+)?(\d[\d,]*(?:\.\d+)?)\s*(million|m|k)?"
    max_price = re.search(
        rf"\b(?:under|below|less than|up to|within|max(?:imum)?|budget(?: of)?|cheaper than)\s+{amount}\b",
        text,
    )
    min_price = re.search(
        rf"\b(?:over|above|more than|at least|from)\s+{amount}\b",
        text,
    )
    if max_price or min_price or re.search(r"\b(sar|sr|riyal)\b", text):
        intent.currency = "SAR"
    if max_price:
        intent.max_price = _amount(max_price.group(1), max_price.group(2))
    if min_price:
        intent.min_price = _amount(min_price.group(1), min_price.group(2))
    # A six-figure SAR cap is a purchase budget. Rent stays rent only when the question says so.
    if intent.purpose is None and intent.max_price is not None and intent.max_price >= 100_000:
        intent.purpose = "sale"
    for word, index in ORDINALS.items():
        if re.search(rf"\b{word}\b", text):
            intent.ordinal = index
            break
    if re.search(r"\b(similar|like this|like that)\b", text):
        intent.similar = True
    if intent.ordinal is not None or intent.similar or re.search(
        r"\b(it|its|that one|this one|tell me more|more about)\b", text
    ):
        intent.anaphoric = True
    named = re.search(r"\b(?:price of|cost of|tell me about|details on|about the)\s+(.+)$", text)
    if named:
        candidate = re.sub(r"\b(please|thanks|thank you)\b", "", named.group(1)).strip(" ?.")
        if candidate and not intent.city:
            intent.title_query = candidate[:120]
        elif candidate and len(candidate.split()) > 3:
            intent.title_query = candidate[:120]
    return intent
