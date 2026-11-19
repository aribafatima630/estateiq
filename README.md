# EstateIQ

AI-Powered Real Estate Intelligence for public DarGlobal and Wasalt information.

**Live application:** [https://estateiq-pjt8.onrender.com](https://estateiq-pjt8.onrender.com)

## Assignment objective

EstateIQ is the submission for the DarGlobal Junior AI Engineer – Applied AI assignment. The brief asks for a chatbot grounded in publicly available DarGlobal and Wasalt data, a free model reached through OpenRouter, a Docker image, and a deployed URL. The assistant answers from the indexed snapshot. It does not invent prices, availability, investment returns, or project details.

When the index has no supporting record, the answer is:

> I couldn't find verified information about this in the currently indexed DarGlobal and Wasalt data.

## Features

- Chat over the indexed DarGlobal and Wasalt snapshot, with no login.
- Source filter for both sites, DarGlobal only, or Wasalt only.
- Property and project cards built from retrieved records, with the original page linked.
- Comparison of the two sources from indexed records.
- Follow-up questions that keep the previous record in the same conversation.
- Refusal when a named place, a named property, or a guaranteed return is not in the index.
- Admin scrape and index rebuild, both protected by a token. Scraping is off on the public service.

## Architecture

```text
Public pages → SQLite records → chunks → MiniLM embeddings → vector index
Question → SQL filters, then vector search when SQL has no hit → OpenRouter → cited answer
```

FastAPI serves the API and the built interface from one container. The OpenRouter key stays on the server. React, TypeScript, and Vite provide the chat interface. SQLite holds the records. Semantic search uses the published `all-MiniLM-L6-v2` weights. The production image runs those weights with NumPy and stores the vectors in `data/indexes/estateiq.npy`. FAISS is used only when that library imports successfully; the deployed image does not include it.

Price, bedroom, city, source, and property-type questions are answered from the database. Open questions use the vector index. A question that names a title the database does not contain is refused, rather than filled with nearby listings.

## Scraping methodology

DarGlobal (`https://darglobal.co.uk/`) is rendered in the browser and sits behind a bot challenge. The collector uses Playwright, reads `robots.txt` and the sitemap, and keeps public project, company, and recent press URLs. It skips the blog, careers, payment, and contact-form URLs. It does not solve challenges. The snapshot contains 90 DarGlobal records.

Wasalt (`https://wasalt.sa/en`) publishes listing data in the public page payload. The collector reads category pages with a normal browser user agent, keeps up to 500 listings across the selected cities and sale or rent pages, and also stores the public homepage and masterplan page. It does not call Wasalt's internal API and does not paginate past the first server-rendered page, because that page did not change with a page query. Contact fields, phone numbers, and WhatsApp details are dropped. A price of zero is stored as missing. Requests are paced, timed out, and retried. The snapshot contains 502 Wasalt records.

Each record keeps its source, source URL, and scrape time. Unchanged content is updated in place. One source failing does not discard the other.

## RAG workflow

1. The question is parsed for city, budget, bedrooms, purpose, source, comparison, follow-up, and a named title.
2. Structured questions are answered with SQL. Property-type totals are counted from the database.
3. If SQL returns nothing, and the question is not a missing title, the vector index returns the closest chunks above the similarity threshold.
4. A place named in the question must appear on the retrieved records. Otherwise the answer is the refusal sentence.
5. The model receives only those records. Cards and citations are copied from the records, not parsed out of the model text.
6. A model URL that is not one of the retrieved source URLs is removed.
7. If the model reports that the context does not support a specific question, that refusal is kept.
8. If the model provider is unavailable, the same records are still shown, with an explicit note that the narrative could not be generated.

## OpenRouter model

The preferred model is `google/gemma-4-31b-it:free`. If that model is rate limited, the server tries other free text models, including `baidu/ernie-5.5-flash-preview:free`, `nvidia/nemotron-3.5-lightning:free`, and `openrouter/free`. Paid models are not used. Free-model availability changes, and a shared pool can return HTTP 429 or an empty completion. EstateIQ treats both as an unavailable model and keeps the retrieved records.

The key is read from `OPENROUTER_API_KEY`. It is not present in the frontend.

## Data sources

| Source | Indexed records | What they are |
| --- | --- | --- |
| DarGlobal | 90 | Developer projects, company pages, and press. Unit prices are stored only when a page publishes one. In this snapshot, DarGlobal prices are empty. |
| Wasalt | 502 | Marketplace listings plus the public homepage and masterplan page. 500 of these are property listings. |

The records were collected on 19 November 2026. `scraped_at` on the stored rows runs from 2026-11-19T06:58:09Z to 2026-11-19T07:00:10Z. Every record has its own source URL. Prices are the figures published at scrape time. They are not a live offer.

## Environment variables

Copy `.env.example` and set values in the host environment. Do not commit the filled file.

| Variable | Purpose |
| --- | --- |
| `OPENROUTER_API_KEY` | Server-side key for OpenRouter |
| `OPENROUTER_MODEL` | Preferred free model |
| `OPENROUTER_FALLBACK_MODELS` | Extra free models, comma separated |
| `ADMIN_TOKEN` | Required header for scrape and index rebuild |
| `DATA_DIR` | Database and index directory. The image uses `/data` |
| `SCRAPER_ENABLED` | `false` on the public service |
| `CORS_ORIGINS` | Allowed browser origin |

## Docker

The repository `Dockerfile` is the production image. It builds the frontend, installs the deployment Python dependencies, downloads the MiniLM weights, and copies the SQLite database and vector index into the image. The process listens on port 8000.

`docker-compose.yml` is the self-hosted layout: the API, a frontend container, and a scrape profile. The public Render service uses the single production image, not the compose split.

## Deployment

The public application runs on Render from that Docker image: [https://estateiq-pjt8.onrender.com](https://estateiq-pjt8.onrender.com). The database and search index are baked into the image. There is no persistent disk. `SCRAPER_ENABLED` is false, and the API key is stored in the host environment, not in the repository.

On the free Render plan the service sleeps after about 15 minutes without traffic. The first request after sleep waits for the instance to start. A new deploy replaces the running disk, including conversations created after the image was built.

## Testing

Backend tests use saved page fixtures. They do not call OpenRouter or the live websites.

```bash
cd backend
python -m pytest -q
```

The live service can be checked at `/api/health` and through the chat box on the public URL.

## Current Limitations and Future Improvements

### Current limitations

- Render's free instance sleeps after about 15 minutes without traffic. The first request after sleep waits for the process to start.
- The host disk is ephemeral. The index survives sleep because it is baked into the image. Conversations created after deploy live only on that instance.
- The public service does not crawl on demand. A fresher snapshot requires a new collection and a new image.
- Wasalt coverage is a capped sample of the first server-rendered category page for each selected city, type, and purpose. It is not the full marketplace.
- A few Wasalt prices are extreme values published on the source page. They are stored as published.
- DarGlobal development pages in this snapshot do not publish a unit price.
- OpenRouter free models share a small quota. The same question can receive a written answer one minute and the unavailable-model note the next. Retrieved cards are still shown.
- The production image evaluates MiniLM with NumPy. It does not ship FAISS or PyTorch.
- `GET /api/stats` reports `last_scrape` as null. Record timestamps are stored, and the committed snapshot has no scrape-run row.
- Chat history on the public instance is not behind a login.

### Future improvements

- Keep the service awake with a paid instance, or accept the cold start and show it in the interface.
- Attach persistent storage so conversations and a refreshed index survive a new deploy.
- Run a scheduled, rate-limited collection and write a scrape-run row, so `last_scrape` reflects the latest successful collection.
- Widen the Wasalt sample only where the public pages expose more listings without calling the internal API.
- Normalize city labels such as Aldammam and Makkah Al Mukarramah, and flag published prices that sit far outside the rest of the sample.
- Cache a successful free-model answer for an identical question, and keep the current fallback across free models when a provider returns 429 or an empty completion.
- Move production retrieval to FAISS on a host that can load it, using the same MiniLM vectors.
- Require a session owner for history listing, so one visitor cannot read another visitor's conversation titles.
