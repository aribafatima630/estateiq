from __future__ import annotations

import asyncio
import logging
import re
from typing import Any
from urllib.parse import urlsplit
from xml.etree import ElementTree

from app.core.config import Settings
from app.schemas.records import Category, Record
from app.utils.text import canonical_url, clean_text, content_hash, stable_id, utc_now

logger = logging.getLogger(__name__)

SITEMAP_NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
HOST = "darglobal.co.uk"
SKIP_PREFIXES = (
    "/blog",
    "/careers",
    "/pay-online",
    "/get-in-touch",
    "/bookyourunit",
    "/privacy",
    "/terms",
    "/thank-you",
    "/success",
    "/internship",
    "/become-a",
    "/become-an",
    "/cookie",
    "/win-a-trip",
    "/campaigns",
    "/new-home-page",
    "/broker-contest",
    "/invest-crypto",
    "/dg-circle",
    "/agents",
)
COMPANY_PREFIXES = (
    "/about",
    "/why-invest",
    "/investor",
    "/faq",
    "/tokenization",
    "/hospitality",
    "/commercial",
    "/exclusive-membership",
    "/partners",
    "/luxury-golf",
    "/insights",
)
PLACES = (
    ("Wadi Safar", "Saudi Arabia"),
    ("Riyadh", "Saudi Arabia"),
    ("Jeddah", "Saudi Arabia"),
    ("Al Marjan", "United Arab Emirates"),
    ("Ras Al Khaimah", "United Arab Emirates"),
    ("Abu Dhabi", "United Arab Emirates"),
    ("Dubai", "United Arab Emirates"),
    ("Simaisma", "Qatar"),
    ("Doha", "Qatar"),
    ("Muscat", "Oman"),
    ("London", "United Kingdom"),
    ("Benahavís", "Spain"),
    ("Benahavis", "Spain"),
    ("Cortesin", "Spain"),
)
COUNTRIES = (
    "Saudi Arabia",
    "United Arab Emirates",
    "Oman",
    "Qatar",
    "United Kingdom",
    "Spain",
)
BRANDS = (
    "Trump",
    "Fendi",
    "Aston Martin",
    "Lamborghini",
    "Missoni",
    "Elie Saab",
    "Pagani",
    "Marriott",
    "W Hotels",
    "Mouawad",
    "Paramount",
    "Nickelodeon",
)
PROPERTY_TYPES = (
    ("Villa", r"\bvillas?\b"),
    ("Apartment", r"\bapartments?\b"),
    ("Mansion", r"\bmansions?\b"),
    ("Plot", r"\bplots?\b"),
    ("Hotel", r"\bhotels?\b"),
    ("Residence", r"\bresidences?\b"),
)
DATE_RE = re.compile(
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\s+\d{1,2},\s+\d{4}\b",
    re.I,
)
MONTHS = {
    "jan": "01",
    "feb": "02",
    "mar": "03",
    "apr": "04",
    "may": "05",
    "jun": "06",
    "jul": "07",
    "aug": "08",
    "sep": "09",
    "oct": "10",
    "nov": "11",
    "dec": "12",
}

EXTRACT_JS = """
() => {
  const root = document.querySelector("main") || document.body;
  const clone = root.cloneNode(true);
  for (const selector of ["script", "style", "noscript", "nav", "footer", "form", "iframe", "svg"]) {
    clone.querySelectorAll(selector).forEach((node) => node.remove());
  }
  const heading = document.querySelector("h1");
  const description = document.querySelector('meta[name="description"]');
  return {
    h1: heading ? heading.innerText : "",
    title: document.title || "",
    description: description ? description.content : "",
    text: (clone.innerText || "").slice(0, 20000)
  };
}
"""


def parse_sitemap(xml_text: str) -> list[tuple[str, str | None]]:
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return []
    pages: list[tuple[str, str | None]] = []
    for node in root.findall("s:url", SITEMAP_NS):
        loc = (node.findtext("s:loc", default="", namespaces=SITEMAP_NS) or "").strip()
        lastmod = (node.findtext("s:lastmod", default="", namespaces=SITEMAP_NS) or "").strip()
        if loc:
            pages.append((loc, lastmod or None))
    return pages


def _path(url: str) -> str:
    return urlsplit(url).path.lower().rstrip("/") or "/"


def select_darglobal_urls(pages: list[tuple[str, str | None]], limit: int) -> list[str]:
    press: list[tuple[str, str]] = []
    chosen: list[str] = []
    seen: set[str] = set()

    def add(url: str) -> None:
        if url in seen:
            return
        parts = urlsplit(url)
        if parts.netloc.lower().endswith(HOST) is False:
            return
        if parts.query or url.lower().endswith(".pdf"):
            return
        path = _path(url)
        if any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in SKIP_PREFIXES):
            return
        seen.add(url)
        chosen.append(url)

    for url, lastmod in pages:
        path = _path(url)
        if path.startswith("/press/") and path != "/press":
            press.append((lastmod or "", url))
    press.sort(reverse=True)
    for url, _lastmod in pages:
        path = _path(url)
        if path in {"/", "/about", "/projects", "/why-invest", "/investor", "/press"}:
            add(url)
        elif path.startswith("/partners"):
            add(url)
        elif any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in COMPANY_PREFIXES):
            add(url)
        elif path.startswith("/projects/"):
            add(url)
    for _lastmod, url in press[:30]:
        add(url)
    for url, _lastmod in pages:
        if len(chosen) >= limit:
            break
        add(url)
    return chosen[:limit]


def classify_url(url: str) -> Category:
    path = _path(url)
    if path.startswith("/press") or path.startswith("/insights"):
        return "news"
    if path in {"/", ""} or any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in COMPANY_PREFIXES):
        if path.startswith("/insights"):
            return "news"
        return "company"
    return "project"


def _places_in(text: str) -> list[tuple[str, str]]:
    haystack = text.lower()
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for place, place_country in PLACES:
        key = place.lower().replace("í", "i")
        if key in seen or place.lower() not in haystack:
            continue
        seen.add(key)
        found.append((place, place_country))
    return found


def infer_location(title: str, text: str = "") -> tuple[str | None, str | None, str | None]:
    """Prefer a place named in the title. Otherwise use the opening of the page."""
    hits = _places_in(title) or _places_in(text[:900])
    found = [f"{place}, {place_country}" for place, place_country in hits[:3]]
    city = hits[0][0] if hits else None
    country = hits[0][1] if hits else None
    if not found:
        haystack = f"{title}\n{text[:900]}".lower()
        for name in COUNTRIES:
            if name.lower() in haystack:
                found.append(name)
                country = country or name
                break
    return ("; ".join(found) or None), city, country


def infer_property_type(title: str, text: str) -> str | None:
    for haystack in (title, text[:700]):
        for label, pattern in PROPERTY_TYPES:
            if re.search(pattern, haystack, re.I):
                return label
    return None


def infer_brands(text: str) -> list[str]:
    found = [brand for brand in BRANDS if re.search(rf"\b{re.escape(brand)}\b", text, re.I)]
    return found


def published_at_from_text(text: str) -> str | None:
    match = DATE_RE.search(text[:800])
    if not match:
        return None
    parts = match.group(0).replace(",", "").split()
    if len(parts) != 3:
        return None
    month = MONTHS.get(parts[0][:3].lower())
    if not month:
        return None
    return f"{int(parts[2]):04d}-{month}-{int(parts[1]):02d}"


def page_to_record(url: str, extracted: dict[str, Any], scraped_at: str) -> Record | None:
    title = clean_text(str(extracted.get("h1") or extracted.get("title") or ""), limit=240)
    title = re.sub(r"\s+\|\s+.*$", "", title).strip() or title
    description = clean_text(str(extracted.get("description") or ""), limit=500)
    body = clean_text(str(extracted.get("text") or ""))
    if description and description not in body:
        body = f"{description}\n\n{body}"
    content = clean_text(body)
    if len(title) < 2 or len(content) < 80:
        return None
    lowered = content.lower()
    if "incapsula" in lowered and len(content) < 400:
        return None
    category = classify_url(url)
    location, city, country = infer_location(title, content)
    brands = infer_brands(f"{title}\n{content[:2500]}")
    property_type = infer_property_type(title, content) if category == "project" else None
    published_at = published_at_from_text(content) if category == "news" else None
    attributes: dict[str, Any] = {}
    if brands:
        attributes["brands"] = brands
    if published_at:
        attributes["published_at"] = published_at
    record = Record(
        id=stable_id("darglobal", canonical_url(url)),
        source="darglobal",
        title=title,
        content=content,
        category=category,
        location=location,
        property_type=property_type,
        attributes=attributes,
        source_url=canonical_url(url),
        scraped_at=scraped_at,
        city=city,
        country=country,
        published_at=published_at,
    )
    record.content_hash = content_hash(record.content)
    return record


async def _dismiss_cookies(page: Any) -> None:
    try:
        button = page.get_by_role("button", name=re.compile(r"accept", re.I))
        if await button.count():
            await button.first.click(timeout=1500)
    except Exception:
        return


async def scrape_darglobal(settings: Settings) -> tuple[list[Record], dict[str, Any]]:
    from playwright.async_api import async_playwright

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
    records: list[Record] = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            locale="en-GB",
        )
        page = await context.new_page()

        async def route_handler(route: Any) -> None:
            if route.request.resource_type in {"image", "media", "font"}:
                await route.abort()
            else:
                await route.continue_()

        await page.route("**/*", route_handler)
        try:
            await page.goto("https://darglobal.co.uk/", wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(2000)
            await _dismiss_cookies(page)
            sitemap_xml = await page.evaluate(
                """async () => {
                    const response = await fetch('/sitemap.xml', { credentials: 'include' });
                    return await response.text();
                }"""
            )
        except Exception as exc:
            stats["errors"].append(f"DarGlobal homepage or sitemap could not be opened: {exc}")
            await browser.close()
            return records, stats

        if "Incapsula" in sitemap_xml and "<loc>" not in sitemap_xml:
            stats["errors"].append(
                "DarGlobal sitemap is still behind a bot challenge. No DarGlobal pages were stored."
            )
            await browser.close()
            return records, stats

        pages = parse_sitemap(sitemap_xml)
        urls = select_darglobal_urls(pages, settings.darglobal_max_pages)
        stats["urls_discovered"] = len(pages)
        if not urls:
            stats["errors"].append("DarGlobal sitemap did not yield any allowed URLs.")
            await browser.close()
            return records, stats

        for index, url in enumerate(urls, start=1):
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(900)
                if index == 1:
                    await _dismiss_cookies(page)
                extracted = await page.evaluate(EXTRACT_JS)
                html_probe = await page.content()
                if "Incapsula" in html_probe and "_Incapsula_Resource" in html_probe and len(extracted.get("text", "")) < 200:
                    raise RuntimeError("Bot challenge page")
                record = page_to_record(url, extracted, scraped_at)
                stats["pages_scraped"] += 1
                if record:
                    records.append(record)
                else:
                    stats["warnings"].append(f"No usable content extracted from {url}")
            except Exception as exc:
                stats["pages_failed"] += 1
                stats["failed_urls"].append({"url": url, "error": str(exc)})
                logger.warning("DarGlobal page failed %s: %s", url, exc)
            await asyncio.sleep(settings.darglobal_delay_seconds)
        await browser.close()

    stats["records"] = len(records)
    logger.info("DarGlobal scrape finished: %s records, %s failed", stats["records"], stats["pages_failed"])
    return records, stats
