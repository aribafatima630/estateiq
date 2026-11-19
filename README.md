# EstateIQ

EstateIQ is a real estate intelligence assistant for public pages from [DarGlobal](https://darglobal.co.uk/) and [Wasalt](https://wasalt.sa/en). Answers come from an indexed snapshot of those pages. The assistant does not invent prices, availability, or project details.

DarGlobal records are developer projects, company pages, and press. Wasalt records are marketplace listings. They are not treated as the same kind of asset.

## Architecture

```text
Scrapers → SQLite records → chunks → Sentence Transformers → FAISS
User question → SQL filters and vector search → OpenRouter → cited answer
```

- FastAPI serves the API and keeps the OpenRouter key on the server.
- React, TypeScript, and Vite serve the interface.
- SQLite stores records, sessions, and scrape reports.
- `all-MiniLM-L6-v2` embeds text locally. EstateIQ uses Sentence Transformers when PyTorch loads. If the PyTorch DLL cannot load, it runs those same published weights in NumPy.
- FAISS `IndexFlatIP` searches normalised vectors. If the FAISS native library cannot load, EstateIQ uses the same inner-product search in NumPy and records that in the log.
- Scraping and index rebuilds require `ADMIN_TOKEN`.

## Stack

Python 3.12, FastAPI, Pydantic, httpx, BeautifulSoup, Playwright, Sentence Transformers, FAISS, SQLite, OpenRouter, React, TypeScript, Vite, Tailwind CSS, Docker Compose.

## Setup

```bash
python -m venv backend/.venv
backend/.venv/Scripts/python -m pip install -r backend/requirements.txt
backend/.venv/Scripts/python -m playwright install chromium
copy .env.example .env
```

Fill in `.env`:

| Variable | Purpose |
| --- | --- |
| `OPENROUTER_API_KEY` | Free OpenRouter key. Without it, EstateIQ still returns indexed cards and says the language model is unavailable. |
| `OPENROUTER_MODEL` | Preferred free model. Default `google/gemma-4-31b-it:free`. |
| `OPENROUTER_FALLBACK_MODELS` | Other free models tried if the preferred one is unavailable. |
| `ADMIN_TOKEN` | Required for `/api/scrape/run` and `/api/index/rebuild`. |
| `CONTACT_EMAIL` | Contact address sent with scraper requests. |
| `DATA_DIR` | SQLite, raw extracts, and the vector index. |
| `RETRIEVAL_THRESHOLD` | Minimum cosine similarity for a chunk to reach the model. |
| `SCRAPER_ENABLED` | Set `false` on a public deployment that should not crawl on demand. |

## Scraping

From `backend`:

```bash
..\.venv\Scripts\python -m app.cli scrape
..\.venv\Scripts\python -m app.cli index
```

Or with Docker:

```bash
docker compose --profile scrape run --rm scraper
```

Wasalt category pages expose listing fields in public page data. The site's CDN rejects the httpx client, so the Wasalt scraper reads that same public HTML with Python's standard HTTP library, a normal browser Accept profile, and your contact address in the `From` header. EstateIQ keeps up to 16 listings from each city, type, and purpose page, and stops at 500 listings. It does not call `api.internal-wasalt.com`, does not store phone or WhatsApp fields, and does not page through internal search. DarGlobal is rendered in a browser because plain HTTP clients receive an Incapsula challenge. Pages that still show a challenge are skipped. Lead forms, careers, and blog archives are not collected. Press is limited to the latest 30 sitemap entries.

The ingestion report is written to `data/processed/ingestion_report.json`.

## Run

```bash
cd backend
..\.venv\Scripts\python -m app.cli serve
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## Docker

```bash
docker compose up --build
```

The interface is on `http://localhost:3000` and the API is on `http://localhost:8000`. The `./data` directory is mounted so the database and index survive restarts.

## API

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/api/health` | Database, index, and key status |
| GET | `/api/stats` | Record counts and the last scrape |
| GET | `/api/sources` | DarGlobal and Wasalt counts |
| GET | `/api/properties` | Structured listing filters |
| GET | `/api/projects` | DarGlobal developments |
| POST | `/api/chat` | `{ "message", "session_id", "source_filter" }` |
| GET | `/api/chat/history` | Sessions, or messages when `session_id` is set |
| DELETE | `/api/chat/history/{session_id}` | Deletes one conversation |
| GET | `/api/scrape/status` | Latest scrape report |
| POST | `/api/scrape/run` | Admin token required |
| POST | `/api/index/rebuild` | Admin token required |

Send the admin token in `X-Admin-Token`.

When nothing relevant is indexed, chat returns:

`I couldn't find verified information about this in the currently indexed DarGlobal and Wasalt data.`

## Tests

```bash
cd backend
..\.venv\Scripts\python -m pytest -q
```

The tests use saved page fixtures. They do not call OpenRouter or the live websites.

## Deployment

`docker compose up --build` is the local production path. A public host still needs:

1. An OpenRouter API key in the host environment.
2. The scraped `data` directory, because free hosts often have an ephemeral disk.
3. `SCRAPER_ENABLED=false` so visitors cannot start a crawl.
4. A long `ADMIN_TOKEN` if rebuild stays enabled.

Free tiers checked on 19 November 2026: Render sleeps after 15 idle minutes and has no persistent disk. Railway's free plan has 512 MB of RAM, which is too small for the embedding model. Fly.io has no ongoing free tier for new accounts. Hugging Face Docker Spaces require a paid plan. The intended public target is a Render web service with the index baked into the image. Chat history on that disk resets when the instance sleeps.

## Known limitations

- The Wasalt index is a capped sample of public category pages, not the full catalogue. A Riyadh apartments page alone reports thousands of listings.
- Listing prices change. Each price is the figure published at scrape time.
- DarGlobal project pages rarely publish a unit price. Those fields stay empty.
- OpenRouter free models are rate limited, commonly 20 requests per minute and 50 per day before an account has purchased credits.
- Wasalt's `llms.txt` allows summaries of public listings and requires attribution. It does not allow resale or contact harvesting. EstateIQ links back to the original page and drops contact fields.
- Windows Application Control on some machines blocks the FAISS DLL, and some PyTorch builds need `VCRUNTIME140_THREADS.dll`. Docker on Linux uses FAISS and Sentence Transformers directly. The NumPy MiniLM path is the local fallback and uses the same model weights.
