from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.request
from typing import Any
from xml.etree import ElementTree

from app.core.config import Settings
from app.schemas.records import Record
from app.utils.text import canonical_url, clean_text, content_hash, parse_int, parse_number, stable_id, utc_now

logger = logging.getLogger(__name__)

SITEMAP_NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
CONTACT_KEYS = {
    "contactdetails",
    "leadcontactinfo",
    "phone",
    "phonenumber",
    "whatsapp",
    "email",
    "mobile",
}

CITIES = ("riyadh", "jeddah", "makkah", "madinah", "dammam", "al-khobar")
PROPERTY_TYPES = ("apartments", "villas", "lands")
PURPOSES = ("sale", "rent")


class RateLimiter:
    def __init__(self, interval: float):
        self.interval = interval
        self._next = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = asyncio.get_running_loop().time()
            if now < self._next:
                await asyncio.sleep(self._next - now)
            self._next = asyncio.get_running_loop().time() + self.interval


def _read_url(url: str, contact_email: str, timeout: float) -> str:
    # Wasalt's CDN returns 403 to the httpx client. urllib receives the same public HTML a browser gets.
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "From": contact_email or "estateiq@localhost",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", "replace")


async def fetch_text(url: str, limiter: RateLimiter, contact_email: str, timeout: float, retries: int = 3) -> str:
    delay = 0.8
    last_error: Exception | None = None
    for attempt in range(retries):
        await limiter.wait()
        try:
            return await asyncio.to_thread(_read_url, url, contact_email, timeout)
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in {429, 500, 502, 503, 504} and exc.code != 403:
                raise
            logger.warning("Fetch failed for %s (attempt %s): HTTP %s", url, attempt + 1, exc.code)
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            logger.warning("Fetch failed for %s (attempt %s): %s", url, attempt + 1, exc)
        await asyncio.sleep(delay)
        delay *= 2
    raise RuntimeError(f"Failed to fetch {url}") from last_error


def _attribute_map(attributes: Any) -> dict[str, Any]:
    mapped: dict[str, Any] = {}
    if not isinstance(attributes, list):
        return mapped
    for item in attributes:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "")
        if key.lower() in CONTACT_KEYS:
            continue
        mapped[key] = item.get("value")
        if item.get("unit"):
            mapped[f"{key}Unit"] = item.get("unit")
    return mapped


def _amenity_names(features: Any) -> list[str]:
    names: list[str] = []
    if not isinstance(features, list):
        return names
    for item in features:
        if isinstance(item, str) and item.strip():
            names.append(item.strip())
        elif isinstance(item, dict):
            name = item.get("name") or item.get("amenityName") or item.get("label")
            if isinstance(name, str) and name.strip():
                names.append(name.strip())
    unique: list[str] = []
    for name in names:
        if name not in unique:
            unique.append(name)
    return unique[:12]


def _property_url(info: dict[str, Any], purpose: str) -> str | None:
    slug = info.get("slug")
    if not isinstance(slug, str) or not slug.strip():
        return None
    return f"https://wasalt.sa/en/property/{purpose}/{slug.strip()}"


def property_to_record(prop: dict[str, Any], page_url: str, scraped_at: str) -> Record | None:
    info = prop.get("propertyInfo") if isinstance(prop.get("propertyInfo"), dict) else {}
    title = clean_text(str(info.get("title") or ""), limit=300)
    if not title:
        return None
    purpose = str(info.get("propertyFor") or "").strip().lower() or None
    if purpose not in {"sale", "rent"}:
        purpose = "sale" if "/sale/" in page_url else "rent" if "/rent/" in page_url else None
    source_url = _property_url(info, purpose or "sale")
    if not source_url:
        return None
    attributes_map = _attribute_map(prop.get("attributes"))
    bedrooms = parse_int(attributes_map.get("noOfBedrooms"))
    bathrooms = parse_int(attributes_map.get("noOfBathrooms"))
    area = parse_number(attributes_map.get("builtUpArea")) or parse_number(prop.get("floorSize"))
    currency = str(info.get("currencyType") or "").strip().upper() or None
    if purpose == "rent":
        price = parse_number(info.get("expectedRent")) or parse_number(info.get("salePrice"))
    else:
        price = parse_number(info.get("salePrice"))
    city = clean_text(str(info.get("city") or ""), limit=120) or None
    district = clean_text(str(info.get("district") or ""), limit=120) or None
    country = clean_text(str(info.get("country") or ""), limit=120) or None
    address = clean_text(str(info.get("address") or ""), limit=240) or None
    location = address or ", ".join(part for part in (district, city, country) if part) or None
    property_type = clean_text(str(info.get("propertySubType") or ""), limit=80) or None
    amenities = _amenity_names(prop.get("featureAmenities"))
    lines = [title]
    if property_type and purpose:
        lines.append(f"{property_type} listed for {purpose} on Wasalt.")
    elif property_type:
        lines.append(f"{property_type} listed on Wasalt.")
    if location:
        lines.append(f"Location: {location}.")
    if city and city not in (location or ""):
        lines.append(f"City: {city}.")
    if district and district not in (location or ""):
        lines.append(f"District: {district}.")
    if price and currency:
        label = "Asking rent" if purpose == "rent" else "Asking price"
        frequency = clean_text(str(info.get("rentFreq") or ""), limit=40)
        extra = f" ({frequency})" if purpose == "rent" and frequency else ""
        lines.append(f"{label}: {int(price) if price.is_integer() else price} {currency}{extra}.")
    elif price:
        lines.append(f"Published price figure: {price}.")
    if bedrooms is not None:
        lines.append(f"Bedrooms: {bedrooms}.")
    if bathrooms is not None:
        lines.append(f"Bathrooms: {bathrooms}.")
    if area is not None:
        lines.append(f"Area: {int(area) if area.is_integer() else area} SQM.")
    furnishing = info.get("furnishingType") or attributes_map.get("furnishingType")
    if isinstance(furnishing, str) and furnishing.strip():
        lines.append(f"Furnishing: {furnishing.strip()}.")
    if amenities:
        lines.append("Amenities listed on the page: " + ", ".join(amenities) + ".")
    lines.append("Record type: Wasalt marketplace listing.")
    content = clean_text(" ".join(lines))
    numeric_id = prop.get("id")
    identity = str(numeric_id) if numeric_id is not None else source_url
    attributes = {
        "wasalt_id": numeric_id,
        "district": district,
        "listing_page": page_url,
        "amenities": amenities,
        "completion_year": attributes_map.get("completionYear"),
        "rent_frequency": info.get("rentFreq") or None,
        "furnishing": furnishing if isinstance(furnishing, str) else None,
    }
    attributes = {key: value for key, value in attributes.items() if value not in (None, "", [])}
    record = Record(
        id=stable_id("wasalt", identity),
        source="wasalt",
        title=title,
        content=content,
        category="property",
        location=location,
        price=price,
        property_type=property_type,
        attributes=attributes,
        source_url=canonical_url(source_url),
        scraped_at=scraped_at,
        city=city,
        country=country,
        currency=currency,
        purpose=purpose,
        bedrooms=bedrooms,
        bathrooms=bathrooms,
        area_sqm=area,
    )
    record.content_hash = content_hash(record.content)
    return record


def parse_category_html(html: str, page_url: str, scraped_at: str | None = None) -> list[Record]:
    scraped_at = scraped_at or utc_now()
    marker = '<script id="__NEXT_DATA__" type="application/json">'
    start = html.find(marker)
    if start < 0:
        return []
    start += len(marker)
    end = html.find("</script>", start)
    if end < 0:
        return []
    try:
        payload = json.loads(html[start:end])
    except json.JSONDecodeError:
        logger.warning("Invalid Next.js data on %s", page_url)
        return []
    page_props = payload.get("props", {}).get("pageProps", {})
    search = page_props.get("searchResult") if isinstance(page_props, dict) else None
    properties = search.get("properties") if isinstance(search, dict) else None
    if not isinstance(properties, list):
        return []
    records: list[Record] = []
    seen: set[str] = set()
    for prop in properties:
        if not isinstance(prop, dict):
            continue
        record = property_to_record(prop, page_url, scraped_at)
        if record and record.id not in seen:
            seen.add(record.id)
            records.append(record)
    return records


def company_record_from_html(html: str, page_url: str, scraped_at: str) -> Record | None:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    chunks: list[str] = []
    for script in soup.select('script[type="application/ld+json"]'):
        raw = script.string or script.get_text() or ""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        nodes = data if isinstance(data, list) else [data]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_type = node.get("@type")
            if node_type == "FAQPage":
                for entity in node.get("mainEntity") or []:
                    if not isinstance(entity, dict):
                        continue
                    question = clean_text(str(entity.get("name") or ""), limit=300)
                    answer_node = entity.get("acceptedAnswer") or {}
                    answer = ""
                    if isinstance(answer_node, dict):
                        answer = clean_text(str(answer_node.get("text") or ""), limit=800)
                    if question and answer:
                        chunks.append(f"{question} {answer}")
            description = node.get("description")
            if isinstance(description, str) and len(description) > 80:
                chunks.append(clean_text(description, limit=1500))
    if not chunks:
        description = soup.find("meta", attrs={"name": "description"})
        if description and description.get("content"):
            chunks.append(clean_text(description["content"], limit=800))
    content = clean_text("\n\n".join(dict.fromkeys(chunks)))
    if len(content) < 80:
        return None
    title = "Wasalt"
    heading = soup.find("h1")
    if heading and heading.get_text(strip=True):
        title = clean_text(heading.get_text(" ", strip=True), limit=180)
    record = Record(
        id=stable_id("wasalt", canonical_url(page_url) + ":company"),
        source="wasalt",
        title=title,
        content=content,
        category="company",
        location="Saudi Arabia",
        city=None,
        country="Saudi Arabia",
        attributes={"kind": "platform"},
        source_url=canonical_url(page_url),
        scraped_at=scraped_at,
    )
    record.content_hash = content_hash(record.content)
    return record


def category_urls() -> list[str]:
    urls: list[str] = []
    for purpose in PURPOSES:
        for property_type in PROPERTY_TYPES:
            for city in CITIES:
                urls.append(f"https://wasalt.sa/en/{property_type}-for-{purpose}-in-{city}")
    return urls


def _sitemap_locs(xml_text: str) -> list[str]:
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return []
    locs = []
    for node in root.findall("s:url", SITEMAP_NS):
        loc = node.findtext("s:loc", default="", namespaces=SITEMAP_NS)
        if loc:
            locs.append(loc.strip())
    return locs


async def scrape_wasalt(settings: Settings) -> tuple[list[Record], dict[str, Any]]:
    scraped_at = utc_now()
    stats: dict[str, Any] = {
        "urls_discovered": 0,
        "pages_scraped": 0,
        "pages_failed": 0,
        "records": 0,
        "errors": [],
        "warnings": [],
        "failed_urls": [],
    }
    limiter = RateLimiter(settings.wasalt_delay_seconds)
    records: list[Record] = []
    seen: set[str] = set()
    seeds = category_urls()
    extra: list[str] = []
    try:
        sitemap_xml = await fetch_text(
            "https://cdn.wasalt.sa/sitemap/category_sitemap_en_sa.xml.gz",
            limiter,
            settings.contact_email,
            settings.request_timeout_seconds,
        )
        for loc in _sitemap_locs(sitemap_xml):
            lower = loc.lower()
            if "/en/" not in lower or "search" in lower:
                continue
            if any(city in lower for city in CITIES) and any(
                token in lower for token in ("apartments-for-sale", "villas-for-sale", "lands-for-sale")
            ):
                if loc not in seeds and loc not in extra:
                    extra.append(loc)
            if len(extra) >= 24:
                break
    except Exception as exc:
        stats["warnings"].append(f"Wasalt category sitemap was not used: {exc}")
        logger.warning("Wasalt sitemap skipped: %s", exc)

    urls = seeds + extra
    stats["urls_discovered"] = len(urls) + 2
    for url in urls:
        if len(seen) >= settings.wasalt_max_listings:
            stats["warnings"].append(
                f"Stopped at the {settings.wasalt_max_listings} listing cap. "
                "Wasalt publishes many more listings than this index keeps."
            )
            break
        try:
            html = await fetch_text(url, limiter, settings.contact_email, settings.request_timeout_seconds)
        except Exception as exc:
            stats["pages_failed"] += 1
            stats["failed_urls"].append({"url": url, "error": str(exc)})
            continue
        page_records = parse_category_html(html, url, scraped_at)[: settings.wasalt_per_page]
        stats["pages_scraped"] += 1
        if not page_records:
            stats["warnings"].append(f"No listings found in {url}")
            continue
        for record in page_records:
            if record.id in seen:
                continue
            if len(seen) >= settings.wasalt_max_listings:
                break
            seen.add(record.id)
            records.append(record)

    for info_url in ("https://wasalt.sa/en", "https://wasalt.sa/en/s/masterplan"):
        try:
            html = await fetch_text(info_url, limiter, settings.contact_email, settings.request_timeout_seconds)
            stats["pages_scraped"] += 1
        except Exception as exc:
            stats["pages_failed"] += 1
            stats["failed_urls"].append({"url": info_url, "error": str(exc)})
            continue
        company = company_record_from_html(html, info_url, scraped_at)
        if company and company.id not in seen:
            if "masterplan" in info_url and company.title == "Wasalt":
                stats["warnings"].append(
                    "The masterplan URL did not expose a distinct public document, so it was not stored as a separate project."
                )
            else:
                seen.add(company.id)
                records.append(company)

    stats["records"] = len(records)
    logger.info(
        "Wasalt scrape finished: %s records from %s pages",
        stats["records"],
        stats["pages_scraped"],
    )
    return records, stats
