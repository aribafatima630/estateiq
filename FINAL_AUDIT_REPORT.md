# EstateIQ final audit

Audit date: 19 November 2026. Public URL tested: https://estateiq-pjt8.onrender.com/

This report records what was inspected and what the live service actually returned. A feature is marked working only when this audit exercised it. Docker was not executed: the Docker CLI is not installed on the machine used for the audit.

## 1. Executive summary

EstateIQ is a deployed RAG assistant over a real snapshot of public DarGlobal and Wasalt pages. The live service loads without authentication, answers from 592 stored records and 976 chunks, and links citations back to the original sites. One citation click in this audit opened `https://darglobal.co.uk/insights/lse-listed-developer-dubai`.

The deployed build does not yet meet the hallucination rule. Asked for the selling price of a property that is not in the index, it returned other Riyadh listings and their prices. Asked which property types are in the index, it refused, even though the database has apartments, villas, land, and one building. The free OpenRouter model was also unavailable for several live questions, including a browser question, "What is DarGlobal?". When that happens the service shows an explicit unavailable-model sentence and the retrieved cards.

Those two answer bugs are fixed in the working tree and covered by tests. The public URL was still running the previous build when this report was written. Eighteen backend tests passed locally. A fresh Docker build was not run.

## 2. Existing architecture

```text
DarGlobal (Playwright, sitemap, capped public pages) ─┐
                                                      ├─ SQLite records ─ chunks ─ MiniLM vectors ─ NumPy inner product
Wasalt (public category HTML, contact fields dropped) ┘
Question ─ intent parse ─ SQL for structured questions ─ vector search only when SQL has no hit
        ─ OpenRouter free model ─ answer plus cards and citations copied from the records
```

One production container builds the React app and serves it with FastAPI. The database and `estateiq.npy` index are copied into the image. `SCRAPER_ENABLED` is false on the public service. The OpenRouter key is an environment variable. The frontend calls relative `/api` paths and does not contain a key.

Production does not import PyTorch or FAISS. It runs the published `all-MiniLM-L6-v2` weights with NumPy. FAISS is a local optional path.

## 3. Assignment compliance checklist

| Requirement | Result |
| --- | --- |
| Scrape public DarGlobal and Wasalt data | Met. 90 DarGlobal and 502 Wasalt records, each with a source URL on darglobal.co.uk or wasalt.sa. |
| Chatbot over that data | Met on the live URL. Answers and cards come from the index. |
| Free OpenRouter model | Met. Live `/api/stats` reported `baidu/ernie-5.5-flash-preview:free` during this audit. The configured preference is `google/gemma-4-31b-it:free`, with other free fallbacks. |
| Docker | The Dockerfile and compose file exist, and Render is running a Docker service. This audit did not build or run the image locally. |
| Deployed public URL | Met. https://estateiq-pjt8.onrender.com/ returned HTTP 200. |
| Working answers grounded in the data | Partial on the deployed build. See the live question log. Named misses could be answered with unrelated prices. |

## 4. Live application test results

Checked on 19 November 2026 against the public URL. The service was already awake. A cold start after the free-tier sleep was not measured.

| Check | Result |
| --- | --- |
| Homepage | HTTP 200. Title: EstateIQ — AI-Powered Real Estate Intelligence. No login. |
| Health | `status=ok`, database true, index ready, 592 records, LLM configured, scraper disabled. |
| Stats | 592 records, 976 chunks, DarGlobal 90, Wasalt 502, categories company 24, news 53, project 15, property 500. `last_scrape` null. `resolved_model` was `baidu/ernie-5.5-flash-preview:free`. |
| Empty message | HTTP 422. The Send button stays disabled while the box is empty. |
| 2001-character message | HTTP 422. |
| Scrape and index rebuild without a token | HTTP 401. |
| Source filter | "What is DarGlobal?" with `source_filter=wasalt` returned the refusal sentence, no citations. |
| Citation click | A DarGlobal citation opened `https://darglobal.co.uk/insights/lse-listed-developer-dubai`. |
| Visual layout | The chat pane, citations, composer, and "592 indexed records" label rendered. The browser pane used for this check was narrow, so a separate desktop and phone viewport pass was not completed. Console errors were not captured. |

Live chat battery, one session, in this order. `llm` is `llm_used` from the API.

| Question | llm | Grounded | What came back |
| --- | --- | --- | --- |
| What is DarGlobal? | true | true | A short definition with 6 DarGlobal citations. The written answer emphasised Dubai and did not describe the full footprint. |
| Tell me about its real estate developments. | true | true | Named DG1 and Da Vinci Tower from one retrieved page. |
| Which countries does DarGlobal operate in? | true | true | UAE, Saudi Arabia, and further countries, with 6 project cards and 8 citations. |
| Tell me about Live Where Luxury Meets Lifestyle: Premium Apartments in Oman | true | true | One DarGlobal project citation. Described as apartments in Muscat. |
| Tell me more about the first project. | true | true | Stayed on that Oman project page. |
| Where is it located? | true | true | Muscat, Oman. Same citation. |
| What additional information is available about it? | true | true | Further details from the same page, including ownership and visa text that the model attributed to the record. |
| What is Wasalt? | true | true | Saudi platform description with Wasalt citations, plus 2 property cards. |
| Show me the available property information. | false | true | Unavailable-model sentence, then a mix of DarGlobal and Wasalt records. |
| Find properties in Riyadh. | true | true | 6 Wasalt property cards, all wasalt.sa citations. The written answer started with apartments for rent. |
| What property types are present in the indexed dataset? | false | false | Refusal sentence. This is wrong. The database has the types. |
| Compare the information available from DarGlobal and Wasalt. | true | true | Comparison table, both hosts, 2 properties and 4 projects. |
| What are the main differences between these two platforms? | true | true | Comparison table and a written distinction between developer and marketplace. |
| Tell me the exact selling price of the Atlantis Mars Penthouse in Riyadh. | false | true | Failed the hallucination check. The answer listed other Wasalt Riyadh prices, including 333.34 SAR and 2000.0 SAR. It did not say the named property is absent. |
| Give me guaranteed investment returns for a DarGlobal project. | false | true | No return figure was invented. The answer was an extract of DarGlobal company and project pages, not an explicit refusal. |
| Tell me details about the Eiffel Tower Residences by DarGlobal in Paris. | false | false | Correct refusal. |
| What is DarGlobal? with the Wasalt filter | false | false | Correct refusal. |

A separate browser send of "What is DarGlobal?" returned the unavailable-model sentence and six DarGlobal citation chips. That was the same question the API had answered with the model a few minutes earlier. Free-model availability is intermittent on the live service.

## 5. Scraping statistics

Queried from `data/processed/estateiq.db` in this audit. Not estimated.

| Measure | Value |
| --- | --- |
| DarGlobal records | 90 (company 22, news 53, project 15) |
| Wasalt records | 502 (property 500, company 2) |
| Indexed chunks | 976, from live `/api/stats` and the deployed index |
| Unique source URLs | 592 |
| Duplicate source URLs | 0 |
| `scraped_at` range | 2026-11-19T06:58:09Z to 2026-11-19T07:00:10Z |
| Rows in `scrape_runs` | 0. This is why live `last_scrape` is null. |
| DarGlobal prices missing | 90 of 90 |
| Wasalt prices missing | 3 of 502 |
| Empty title, empty URL, or content shorter than 40 characters | 0 |
| City missing | 14 |
| Location empty | 8 |
| Wasalt property types | Apartment 191, Villa 181, Land 127, Building 1, missing type 2 |
| Wasalt cities | Jeddah 96, Riyadh 94, Khobar 80, Aldammam 80, Makkah Al Mukarramah 76, Madinah 74, city null 2 |
| Records whose text contains "whatsapp" or "+966" | 75, all DarGlobal. Wasalt rows: 0 |

Wasalt sale prices in the snapshot run from 3,500 to 83,200,000,000 SAR. Rent prices run from 333.34 to 22,974,075,000 SAR. Those extremes are stored as published. They were not corrected.

DarGlobal project titles in the snapshot include pages for Dubai, London, Benahavís, Muscat, Simaisma, Al Marjan, Wadi Safar, and Jeddah. Several project pages share the title "Buy Modern Apartments & Exclusive Villas" with different locations. That is the page title that was collected, not a generated listing.

The collectors pace requests, set timeouts, and retry Wasalt fetches. DarGlobal selection skips blog, contact-form, and similar URLs. Wasalt parsing drops phone, WhatsApp, and lead-contact fields. The audit did not re-crawl either site and did not re-read robots.txt during this pass. Failed scrape operations are not recorded, because `scrape_runs` is empty.

The committed snapshot contained 14 chat sessions and 44 messages from earlier testing. They did not contain an API key. Those rows were deleted from the local database after the audit count. The public URL still has whatever conversations were written on the running instance until a new image is deployed.

## 6. RAG evaluation

What held up on the live service:

- Follow-up questions stayed on the Oman project and answered Muscat for "Where is it located?".
- The Paris project that is not indexed was refused.
- A Wasalt-only filter did not answer a DarGlobal question.
- Comparison questions returned a comparison table built beside the model text.
- Citations in the tested answers used darglobal.co.uk or wasalt.sa URLs.
- SQL filters for Riyadh listings returned Wasalt property cards.

What failed on the deployed build:

- A named property that is not indexed, asked with "in Riyadh", was answered with other Riyadh prices. The city filter treated the question as a Riyadh listing query. The model then signalled that the context was insufficient, and the server replaced that refusal with an extract of the retrieved listings.
- "What property types are present in the indexed dataset?" was wiped by the place filter. The phrase "in the indexed dataset" was treated as a place name, no record contained that phrase, and the service refused.
- "Show me the available property information" mixed DarGlobal and Wasalt because the question has no city or type constraint.
- Vector search is skipped once SQL returns rows. That keeps budget and city answers fast. It also means a bad SQL interpretation cannot be corrected by retrieval.

Local checks after the fix, using the real database and a fake model so OpenRouter was not called:

- The Atlantis Mars Penthouse question now returns the refusal sentence, with no property cards.
- The property-type question now returns the database counts: Wasalt Apartment 191, Villa 181, Land 127, Building 1, and DarGlobal Villa 13, Apartment 2.
- The guaranteed-return question now returns the refusal sentence. No indexed page in the retrieval path stated a guaranteed return.

## 7. OpenRouter evaluation

- The key is read from the environment. A search of the repository source found no embedded OpenRouter, GitHub, or Render key.
- The frontend has no model key.
- Live stats showed a resolved free model, `baidu/ernie-5.5-flash-preview:free`, which means the preferred Gemma model was not the one serving at that moment. The client walks free models and cools a model after HTTP 429.
- Empty completions are treated as failure. The user then sees the unavailable-model sentence and the retrieved cards. This happened in the browser during this audit and on "Show me the available property information".
- Free models are shared and rate limited. Availability is not stable. The audit observed both a written answer and the unavailable sentence for "What is DarGlobal?" within the same session.
- Timeouts and a single retry for server errors exist in the client. This audit did not force a timeout.

## 8. Backend audit

| Endpoint | Observed |
| --- | --- |
| GET `/api/health` | 200 and the payload above. |
| GET `/api/stats` | 200. `last_scrape` null. |
| GET `/api/sources` | 200. DarGlobal 90, Wasalt 502, with the public site URLs. |
| POST `/api/chat` | 200 for the questions above. 422 for empty and over-long messages. |
| POST `/api/scrape/run` without a token | 401. Scraping is also disabled in the public settings, which would return 403 after a valid token. |
| POST `/api/index/rebuild` without a token | 401. |
| GET `/api/chat/history` | Implemented and public. Anyone who can call the API can list session titles on that instance. |

SQL values are bound with placeholders. The admin token is compared with `compare_digest`. Uvicorn reload is off. Debug mode was not enabled in the serve command. A missing model does not take down retrieval: the unavailable sentence is returned with the records. A missing named record does not call the model.

## 9. Frontend audit

The live page identifies itself as EstateIQ, states that answers stay tied to indexed DarGlobal and Wasalt pages, and shows the record count once stats load. Suggested prompts, source filters, history, and a clear-conversation control are present. Property and project cards are links with `target=_blank`. The citation clicked in this audit opened the DarGlobal article.

When the model is down, the transcript shows the unavailable sentence, a dense extract of record titles, the citation chips, and the line "Narrative generation was unavailable. The cards are from the index." That state is honest and looks rougher than a written answer.

This audit did not complete a separate wide desktop pass or a device-emulated phone pass, and it did not record the browser console. The earlier local layout work is not restated here as a live result.

## 10. Docker audit

| Item | Finding |
| --- | --- |
| Dockerfile | Multi-stage. Node builds the frontend. Python 3.12 installs `requirements-deploy.txt`, downloads the MiniLM weights, copies the database, the `.npy` index, and `meta.json`, and starts `python -m app.cli serve` on port 8000. `SCRAPER_ENABLED=false`. |
| docker-compose.yml | Separate API and frontend services, a data volume, and a scrape profile. Not the layout Render runs. |
| .dockerignore | Excludes `.env`, virtualenvs, raw data, and tests. |
| Fresh build | Not run. `docker` is not installed on this machine. |
| Persistence | The image contains the snapshot. Compose would mount `./data`. Render has no disk attached, so the running container's new conversations live only until the instance is replaced. |

## 11. Deployment audit

The public URL responded in this audit with the baked snapshot: 592 records, index ready, scraper off, model configured. That is evidence the deployed image contains the database and the index. It is not evidence of a cold-start recovery, a health-check configuration review inside Render, memory use, or the deploy logs. Those were not opened in this pass.

Free-tier sleep is a known platform limit and is described in the README. It was not timed in this audit because the service was already up.

## 12. Security findings

- No API key was found in the source search.
- Admin scrape and rebuild reject a missing token with 401 when a token is configured.
- Public scraping is disabled.
- Queries are parameterized.
- Chat history is unauthenticated. Session titles from anyone using the public instance can be listed.
- The snapshot database previously contained 14 sessions and 44 test messages. They held no key. They have been removed from the local database so the next image does not ship them.
- DarGlobal page text still contains phone numbers that were part of the public pages. Wasalt contact fields were not stored.
- The admin token and the OpenRouter key live in the gitignored `.env` and in the host environment. They are not repeated here.

## 13. Test results

Before the fixes: 14 passed.

After the fixes: 18 passed in 3.44 seconds. The four new tests cover a missing named property, property-type counts, a model refusal that must not be replaced with cards, and a guaranteed-return question whose pages do not state a guarantee.

The tests use fixtures and a fake model. They do not call OpenRouter or the live websites. Docker tests were not run.

## 14. Remaining limitations

- The public URL does not include the retrieval fixes until a new image is deployed.
- Free Render sleeps, and this audit did not measure the wake time.
- The index is baked into the image. There is no persistent disk. A new deploy replaces conversations stored only on the running instance.
- `last_scrape` stays null until a scrape-run row is stored.
- Wasalt is a capped sample. Some published prices are extreme.
- DarGlobal unit prices are absent in this snapshot.
- Free OpenRouter models can refuse to answer or return an empty completion. The cards remain, and the copy says the narrative was unavailable.
- City labels are stored as collected, including "Aldammam" and "Makkah Al Mukarramah".
- History listing is public.

## 15. Improvements implemented

In the working tree, after the live audit:

- A named title that the database does not contain is no longer filled with other listings from the same city.
- A model refusal is kept for questions that are not a browse, comparison, follow-up, or catalogue question.
- Questions that ask for a guaranteed figure are refused unless a retrieved page uses that word.
- "What property types are present" is answered from `GROUP BY` counts on the database.
- The place filter ignores a phrase when any token is a known place or a stopword such as "dataset" or "indexed".
- README now matches the implementation: assignment objective, scraping, RAG, the free model, environment variables, Docker, deployment, tests, and a section titled "Current Limitations and Future Improvements".
- Test chat rows were removed from the local snapshot database. Record counts are unchanged at 592.

Not changed: the scrapers, the embedding implementation, the card UI, and the OpenRouter fallback order.

## 16. Final submission recommendation

The project is a credible submission once the retrieval fixes are on the public URL. The deployed build already shows real scraped data, a free OpenRouter model, citations that open the source sites, Docker packaging, and a public address. It should not be submitted on the current live build alone, because that build can present other Riyadh prices as the answer to a property that is not in the index.

| Area | Score | Evidence |
| --- | --- | --- |
| Assignment compliance | 8 | All six deliverables exist. The live hallucination miss keeps it below 9. |
| Web scraping | 8 | 592 real source URLs, contacts dropped on Wasalt, timeouts and retries in code. No scrape-run log and no re-crawl in this audit. |
| Data engineering | 7 | Normalized records and unique URLs. Extreme published prices, uneven city labels, and an empty scrape-run table. |
| RAG architecture | 6 | Hybrid SQL and vector design is sound. The live named-price and property-type failures are retrieval bugs. Fixed locally, not yet deployed. |
| LLM integration | 7 | Free models, server-side key, fallbacks, explicit unavailable state. Availability was intermittent during the audit. |
| Answer accuracy | 6 | Countries, follow-up location, comparison, and the Paris refusal were right. The Mars price answer was wrong. |
| Source citations | 8 | Citations matched retrieved hosts. A live click opened the DarGlobal article. Wrong retrieval still produces real links. |
| Backend engineering | 8 | Validation, status codes, parameterized SQL, admin token, scraper off in public. Public history listing. |
| Frontend experience | 7 | Coherent product UI on the live page. The unavailable-model state is readable and plain. Wide and phone layouts were not both verified in this pass. |
| Docker | 5 | Dockerfile and compose are present and Render is serving a container. This audit did not build the image. |
| Deployment | 8 | Public URL healthy with the baked 592-record index. Cold start, disk, and Render logs were not verified. |
| Code quality | 7 | 18 passing fixture tests after the fix. Intent routing is still a pile of regular expressions. |
| Security | 7 | No key in source, admin routes locked, Wasalt contacts dropped. Public history, and test transcripts were in the snapshot until this cleanup. |
| Documentation | 8 | README now describes the live system, the model, Docker, and the real limits. It no longer tells a reviewer to use a local URL as the product. |

Scores reflect the system that was tested. The local fixes raise the RAG and answer-accuracy position only after they are deployed and the same three questions are repeated on the public URL.
