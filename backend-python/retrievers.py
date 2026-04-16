# """Retrieval agents for PubMed, OpenAlex, and ClinicalTrials.gov.

# Each fetcher retrieves a broad candidate pool (50-100+ results),
# normalizes them into a common schema, and handles errors gracefully.
# """

# from __future__ import annotations
# import asyncio
# import os
# import xml.etree.ElementTree as ET

# import httpx

# PUBMED_MAX = int(os.getenv("PUBMED_MAX_RESULTS", "100"))
# OPENALEX_MAX = int(os.getenv("OPENALEX_MAX_RESULTS", "100"))
# TRIALS_MAX = int(os.getenv("CLINICAL_TRIALS_MAX_RESULTS", "50"))

# TIMEOUT = httpx.Timeout(15.0, connect=10.0)


# # ── PubMed ─────────────────────────────────────────────────────────────────

# async def fetch_pubmed(query: str, max_results: int = PUBMED_MAX) -> list[dict]:
#     """Two-step PubMed fetch: esearch for IDs, then efetch for metadata."""
#     async with httpx.AsyncClient(timeout=TIMEOUT) as client:
#         # Step 1: Search for IDs
#         search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
#         search_params = {
#             "db": "pubmed",
#             "term": query,
#             "retmax": max_results,
#             "sort": "relevance",
#             "retmode": "json",
#         }
#         id_list = []
#         for attempt in range(3):
#             try:
#                 resp = await client.get(search_url, params=search_params)
#                 if resp.status_code == 429:
#                     print(f"[PubMed] Search rate limited. Retrying in {attempt + 1}s...")
#                     await asyncio.sleep(1.0 + attempt)
#                     continue
#                 resp.raise_for_status()
#                 data = resp.json()
#                 id_list = data.get("esearchresult", {}).get("idlist", [])
#                 break
#             except Exception as e:
#                 if attempt == 2:
#                     print(f"[PubMed] Search failed: {e}")
#                 else:
#                     await asyncio.sleep(1.0 + attempt)

#         if not id_list:
#             return []

#         # Step 2: Fetch details in batches of 50
#         publications = []
#         for i in range(0, len(id_list), 50):
#             batch_ids = id_list[i : i + 50]
#             fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
#             fetch_params = {
#                 "db": "pubmed",
#                 "id": ",".join(batch_ids),
#                 "retmode": "xml",
#             }
#             for attempt in range(3):
#                 try:
#                     resp = await client.get(fetch_url, params=fetch_params)
#                     if resp.status_code == 429:
#                         print(f"[PubMed] Rate limited (429). Retrying in {attempt + 1}s...")
#                         await asyncio.sleep(1.0 + attempt)
#                         continue
#                     resp.raise_for_status()
#                     publications.extend(_parse_pubmed_xml(resp.text))
#                     break
#                 except Exception as e:
#                     if attempt == 2:
#                         print(f"[PubMed] Fetch batch failed: {e}")
#                     else:
#                         await asyncio.sleep(1.0 + attempt)

#             # Polite delay between batches
#             if i + 50 < len(id_list):
#                 await asyncio.sleep(0.5)

#         return publications


# def _parse_pubmed_xml(xml_text: str) -> list[dict]:
#     """Parse PubMed efetch XML into normalized publication dicts."""
#     pubs = []
#     try:
#         root = ET.fromstring(xml_text)
#     except ET.ParseError:
#         return pubs

#     for article in root.findall(".//PubmedArticle"):
#         try:
#             medline = article.find(".//MedlineCitation")
#             art = medline.find(".//Article") if medline is not None else None
#             if art is None:
#                 continue

#             title_el = art.find(".//ArticleTitle")
#             title = title_el.text if title_el is not None and title_el.text else ""

#             # Abstract
#             abstract_parts = []
#             for abs_text in art.findall(".//Abstract/AbstractText"):
#                 label = abs_text.get("Label", "")
#                 text = abs_text.text or ""
#                 if label:
#                     abstract_parts.append(f"{label}: {text}")
#                 else:
#                     abstract_parts.append(text)
#             abstract = " ".join(abstract_parts)

#             # Authors
#             authors = []
#             for author in art.findall(".//AuthorList/Author"):
#                 last = author.find("LastName")
#                 first = author.find("ForeName")
#                 if last is not None and last.text:
#                     name = last.text
#                     if first is not None and first.text:
#                         name = f"{first.text} {last.text}"
#                     authors.append(name)

#             # Year
#             year = None
#             pub_date = art.find(".//Journal/JournalIssue/PubDate/Year")
#             if pub_date is not None and pub_date.text:
#                 try:
#                     year = int(pub_date.text)
#                 except ValueError:
#                     pass

#             # PMID
#             pmid_el = medline.find(".//PMID")
#             pmid = pmid_el.text if pmid_el is not None else ""
#             url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""

#             pubs.append({
#                 "title": title,
#                 "abstract": abstract[:2000],  # Cap abstract length
#                 "authors": authors[:10],
#                 "year": year,
#                 "source": "PubMed",
#                 "url": url,
#                 "doi": "",
#                 "relevance_score": 0.0,
#             })
#         except Exception:
#             continue

#     return pubs


# # ── OpenAlex ───────────────────────────────────────────────────────────────

# async def fetch_openalex(query: str, max_results: int = OPENALEX_MAX) -> list[dict]:
#     """Fetch publications from OpenAlex with pagination."""
#     publications = []
#     per_page = min(max_results, 50)
#     pages = (max_results + per_page - 1) // per_page

#     async with httpx.AsyncClient(timeout=TIMEOUT) as client:
#         for page in range(1, pages + 1):
#             url = "https://api.openalex.org/works"
#             params = {
#                 "search": query,
#                 "per-page": per_page,
#                 "page": page,
#                 "sort": "relevance_score:desc",
#                 "filter": "from_publication_date:2018-01-01",
#                 "mailto": "curalink@example.com",  # Polite pool
#             }
#             try:
#                 resp = await client.get(url, params=params)
#                 resp.raise_for_status()
#                 data = resp.json()
#                 results = data.get("results", [])
#                 if not results:
#                     break
#                 publications.extend(_parse_openalex_results(results))
#             except Exception as e:
#                 print(f"[OpenAlex] Page {page} failed: {e}")
#                 break

#             if page < pages:
#                 await asyncio.sleep(0.2)

#     return publications


# def _parse_openalex_results(results: list[dict]) -> list[dict]:
#     """Normalize OpenAlex works into publication dicts."""
#     pubs = []
#     for work in results:
#         title = work.get("title", "") or ""
#         if not title:
#             continue

#         # Abstract (OpenAlex returns inverted index)
#         abstract = ""
#         inv_abstract = work.get("abstract_inverted_index")
#         if inv_abstract:
#             try:
#                 word_positions = []
#                 for word, positions in inv_abstract.items():
#                     for pos in positions:
#                         word_positions.append((pos, word))
#                 word_positions.sort()
#                 abstract = " ".join(w for _, w in word_positions)[:2000]
#             except Exception:
#                 pass

#         # Authors
#         authors = []
#         for authorship in work.get("authorships", [])[:10]:
#             author = authorship.get("author", {})
#             name = author.get("display_name", "")
#             if name:
#                 authors.append(name)

#         # Year
#         year = work.get("publication_year")

#         # URL and DOI
#         doi = work.get("doi", "") or ""
#         url = doi if doi.startswith("http") else work.get("id", "")

#         pubs.append({
#             "title": title,
#             "abstract": abstract,
#             "authors": authors,
#             "year": year,
#             "source": "OpenAlex",
#             "url": url,
#             "doi": doi,
#             "relevance_score": 0.0,
#         })

#     return pubs


# # ── ClinicalTrials.gov ─────────────────────────────────────────────────────

# async def fetch_clinical_trials(
#     disease: str,
#     query: str = "",
#     location: str = "",
#     max_results: int = TRIALS_MAX,
# ) -> list[dict]:
#     """Fetch trials from ClinicalTrials.gov API v2."""
#     async with httpx.AsyncClient(timeout=TIMEOUT) as client:
#         url = "https://clinicaltrials.gov/api/v2/studies"
#         params = {
#             "query.cond": disease,
#             "pageSize": min(max_results, 100),
#             "format": "json",
#         }
#         if query:
#             params["query.intr"] = query
#         if location:
#             params["query.locn"] = location

#         # Fetch both recruiting and completed
#         all_trials = []
#         for status in ["RECRUITING", "COMPLETED"]:
#             params["filter.overallStatus"] = status
#             try:
#                 resp = await client.get(url, params=params)
#                 resp.raise_for_status()
#                 data = resp.json()
#                 studies = data.get("studies", [])
#                 all_trials.extend(_parse_trials(studies))
#             except Exception as e:
#                 print(f"[ClinicalTrials] {status} fetch failed: {e}")
#                 continue

#         return all_trials[:max_results]


# def _parse_trials(studies: list[dict]) -> list[dict]:
#     """Normalize ClinicalTrials.gov study objects."""
#     trials = []
#     for study in studies:
#         try:
#             protocol = study.get("protocolSection", {})
#             id_module = protocol.get("identificationModule", {})
#             status_module = protocol.get("statusModule", {})
#             desc_module = protocol.get("descriptionModule", {})
#             elig_module = protocol.get("eligibilityModule", {})
#             contacts_module = protocol.get("contactsLocationsModule", {})
#             cond_module = protocol.get("conditionsModule", {})
#             interv_module = protocol.get("armsInterventionsModule", {})

#             nct_id = id_module.get("nctId", "")
#             title = id_module.get("briefTitle", "") or id_module.get("officialTitle", "")

#             # Status
#             status = status_module.get("overallStatus", "")

#             # Conditions
#             conditions = cond_module.get("conditions", [])

#             # Interventions
#             interventions = []
#             for interv in interv_module.get("interventions", []):
#                 name = interv.get("name", "")
#                 if name:
#                     interventions.append(name)

#             # Eligibility
#             eligibility = elig_module.get("eligibilityCriteria", "")[:500]

#             # Locations
#             locations = []
#             for loc in contacts_module.get("locations", [])[:5]:
#                 facility = loc.get("facility", "")
#                 city = loc.get("city", "")
#                 country = loc.get("country", "")
#                 loc_str = ", ".join(filter(None, [facility, city, country]))
#                 if loc_str:
#                     locations.append(loc_str)

#             # Contacts
#             contacts = []
#             for contact in contacts_module.get("centralContacts", [])[:3]:
#                 name = contact.get("name", "")
#                 email = contact.get("email", "")
#                 if name:
#                     contacts.append(f"{name} ({email})" if email else name)

#             url = f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else ""

#             trials.append({
#                 "title": title,
#                 "nct_id": nct_id,
#                 "status": status,
#                 "conditions": conditions,
#                 "interventions": interventions,
#                 "eligibility": eligibility,
#                 "locations": locations,
#                 "contacts": contacts,
#                 "url": url,
#                 "relevance_score": 0.0,
#             })
#         except Exception:
#             continue

#     return trials


# # ── Parallel fetch all sources ──────────────────────────────────────────────

# async def fetch_all_sources(
#     queries: list[str],
#     disease: str,
#     location: str = "",
# ) -> tuple[list[dict], list[dict]]:
#     """Run all retrieval agents in parallel across multiple expanded queries."""
#     pub_tasks = []
#     trial_tasks = []

#     for q in queries:
#         pub_tasks.append(fetch_pubmed(q))
#         pub_tasks.append(fetch_openalex(q))

#     # Trials use disease + first query as intervention
#     primary_query = queries[0] if queries else disease
#     trial_tasks.append(fetch_clinical_trials(disease, primary_query, location))

#     # Run everything in parallel
#     all_results = await asyncio.gather(*pub_tasks, *trial_tasks, return_exceptions=True)

#     # Separate publications and trials
#     all_pubs = []
#     all_trials = []

#     pub_count = len(pub_tasks)
#     for i, result in enumerate(all_results):
#         if isinstance(result, Exception):
#             print(f"[Retrieval] Task {i} failed: {result}")
#             continue
#         if i < pub_count:
#             all_pubs.extend(result)
#         else:
#             all_trials.extend(result)

#     return all_pubs, all_trials
# -----------------------------------------------------------------------------
"""Retrieval agents for PubMed, OpenAlex, and ClinicalTrials.gov.

PATCHED v2 - Fixes PubMed 429 rate limiting issue:
1. Global semaphore to serialize PubMed requests (max 3/sec without key, 10/sec with)
2. Optional NCBI_API_KEY support (free, 10 req/sec)
3. Entrez History (WebEnv + query_key) for efficient batching - 1 esearch, 1 efetch
4. Exponential backoff on 429 errors
5. Reduced default max_results to avoid huge batch fetches
"""

from __future__ import annotations
import asyncio
import os
import xml.etree.ElementTree as ET
from datetime import datetime

import httpx

PUBMED_MAX = int(os.getenv("PUBMED_MAX_RESULTS", "60"))  # Reduced from 100
OPENALEX_MAX = int(os.getenv("OPENALEX_MAX_RESULTS", "100"))
TRIALS_MAX = int(os.getenv("CLINICAL_TRIALS_MAX_RESULTS", "50"))
NCBI_API_KEY = os.getenv("NCBI_API_KEY", "")  # Optional but recommended

TIMEOUT = httpx.Timeout(20.0, connect=10.0)

# ── Global rate limiter for PubMed ────────────────────────────────────────
# NCBI allows 3 req/sec without key, 10 req/sec with key.
# We use a semaphore to cap concurrency across all parallel tasks.
_PUBMED_MAX_CONCURRENT = 2 if not NCBI_API_KEY else 5
_pubmed_semaphore = asyncio.Semaphore(_PUBMED_MAX_CONCURRENT)
_pubmed_min_interval = 0.35 if not NCBI_API_KEY else 0.12  # 3/sec or 10/sec
_pubmed_last_request = 0.0
_pubmed_lock = asyncio.Lock()


async def _pubmed_rate_limit():
    """Enforce global min interval between PubMed requests."""
    global _pubmed_last_request
    async with _pubmed_lock:
        now = asyncio.get_event_loop().time()
        wait = _pubmed_min_interval - (now - _pubmed_last_request)
        if wait > 0:
            await asyncio.sleep(wait)
        _pubmed_last_request = asyncio.get_event_loop().time()


async def _pubmed_request_with_retry(client, url, params, max_retries=3):
    """Make a PubMed request with rate limiting and exponential backoff on 429."""
    for attempt in range(max_retries):
        async with _pubmed_semaphore:
            await _pubmed_rate_limit()
            try:
                resp = await client.get(url, params=params)
                if resp.status_code == 429:
                    wait = 2 ** attempt  # 1s, 2s, 4s
                    print(f"[PubMed] 429 on attempt {attempt+1}, waiting {wait}s")
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429 and attempt < max_retries - 1:
                    wait = 2 ** attempt
                    print(f"[PubMed] 429 caught, retry in {wait}s")
                    await asyncio.sleep(wait)
                    continue
                raise
    return None


# ── PubMed (with Entrez History for efficient batching) ───────────────────

async def fetch_pubmed(
    query: str,
    max_results: int = PUBMED_MAX,
    sort_by_date: bool = True,
) -> list[dict]:
    """PubMed fetch using Entrez History for single-shot batch retrieval.

    FIX v2:
    - Uses usehistory=y in esearch to get WebEnv + query_key
    - Single efetch with WebEnv fetches ALL results in one request
    - No more batched efetch calls that trigger 429s
    - Respects NCBI rate limits via semaphore
    - Adds API key if NCBI_API_KEY env var set
    """
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        # Step 1: esearch with history
        search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"

        if sort_by_date:
            term = f'({query}) AND ("2020"[Date - Publication] : "3000"[Date - Publication])'
        else:
            term = query

        search_params = {
            "db": "pubmed",
            "term": term,
            "retmax": max_results,
            "sort": "pub+date" if sort_by_date else "relevance",
            "retmode": "json",
            "usehistory": "y",  # KEY FIX: Use Entrez History
        }
        if NCBI_API_KEY:
            search_params["api_key"] = NCBI_API_KEY

        try:
            resp = await _pubmed_request_with_retry(client, search_url, search_params)
            if not resp:
                return []
            data = resp.json()
            esearch_result = data.get("esearchresult", {})
            id_list = esearch_result.get("idlist", [])
            webenv = esearch_result.get("webenv", "")
            query_key = esearch_result.get("querykey", "")
            print(f"[PubMed] Query '{query[:40]}...' → {len(id_list)} IDs")
        except Exception as e:
            print(f"[PubMed] Search failed: {e}")
            return []

        if not id_list or not webenv:
            return []

        # Step 2: SINGLE efetch using WebEnv (no batching, no 429)
        fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        fetch_params = {
            "db": "pubmed",
            "query_key": query_key,
            "WebEnv": webenv,
            "retmax": len(id_list),
            "retmode": "xml",
        }
        if NCBI_API_KEY:
            fetch_params["api_key"] = NCBI_API_KEY

        try:
            resp = await _pubmed_request_with_retry(client, fetch_url, fetch_params)
            if not resp:
                return []
            publications = _parse_pubmed_xml(resp.text)
            print(f"[PubMed] Parsed {len(publications)} publications (single fetch)")
            return publications
        except Exception as e:
            print(f"[PubMed] Fetch failed: {e}")
            return []


def _parse_pubmed_xml(xml_text: str) -> list[dict]:
    """Parse PubMed efetch XML into normalized publication dicts."""
    pubs = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        print(f"[PubMed] XML parse error: {e}")
        return pubs

    for article in root.findall(".//PubmedArticle"):
        try:
            medline = article.find(".//MedlineCitation")
            art = medline.find(".//Article") if medline is not None else None
            if art is None:
                continue

            title_el = art.find(".//ArticleTitle")
            title = title_el.text if title_el is not None and title_el.text else ""

            abstract_parts = []
            for abs_text in art.findall(".//Abstract/AbstractText"):
                label = abs_text.get("Label", "")
                text = abs_text.text or ""
                if label:
                    abstract_parts.append(f"{label}: {text}")
                else:
                    abstract_parts.append(text)
            abstract = " ".join(abstract_parts)

            authors = []
            for author in art.findall(".//AuthorList/Author"):
                last = author.find("LastName")
                first = author.find("ForeName")
                if last is not None and last.text:
                    name = last.text
                    if first is not None and first.text:
                        name = f"{first.text} {last.text}"
                    authors.append(name)

            year = None
            pub_date = art.find(".//Journal/JournalIssue/PubDate/Year")
            if pub_date is not None and pub_date.text:
                try:
                    year = int(pub_date.text)
                except ValueError:
                    pass

            pmid_el = medline.find(".//PMID")
            pmid = pmid_el.text if pmid_el is not None else ""
            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""

            pubs.append({
                "title": title,
                "abstract": abstract[:2000],
                "authors": authors[:10],
                "year": year,
                "source": "PubMed",
                "url": url,
                "doi": "",
                "relevance_score": 0.0,
            })
        except Exception:
            continue

    return pubs


# ── OpenAlex ───────────────────────────────────────────────────────────────

async def fetch_openalex(
    query: str,
    max_results: int = OPENALEX_MAX,
    sort_by_date: bool = True,
) -> list[dict]:
    """OpenAlex fetch - no rate limit issues, keep as-is."""
    publications = []
    per_page = min(max_results, 50)
    pages = (max_results + per_page - 1) // per_page

    recent_cutoff = f"{datetime.now().year - 5}-01-01"

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for page in range(1, pages + 1):
            url = "https://api.openalex.org/works"
            params = {
                "search": query,
                "per-page": per_page,
                "page": page,
                "sort": "publication_date:desc" if sort_by_date else "relevance_score:desc",
                "filter": f"from_publication_date:{recent_cutoff},type:article",  # FIX: articles only
                "mailto": "curalink@example.com",
            }
            try:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                results = data.get("results", [])
                if not results:
                    break
                parsed = _parse_openalex_results(results)
                publications.extend(parsed)
            except Exception as e:
                print(f"[OpenAlex] Page {page} failed: {e}")
                break

            if page < pages:
                await asyncio.sleep(0.2)

    print(f"[OpenAlex] Total for '{query[:40]}...': {len(publications)} publications")
    return publications


def _parse_openalex_results(results: list[dict]) -> list[dict]:
    """Normalize OpenAlex works into publication dicts."""
    pubs = []
    for work in results:
        title = work.get("title", "") or ""
        if not title:
            continue

        # FIX: Filter out non-medical work types
        work_type = work.get("type", "")
        if work_type in {"dataset", "grant", "other"}:
            continue

        abstract = ""
        inv_abstract = work.get("abstract_inverted_index")
        if inv_abstract:
            try:
                word_positions = []
                for word, positions in inv_abstract.items():
                    for pos in positions:
                        word_positions.append((pos, word))
                word_positions.sort()
                abstract = " ".join(w for _, w in word_positions)[:2000]
            except Exception:
                pass

        authors = []
        for authorship in work.get("authorships", [])[:10]:
            author = authorship.get("author", {})
            name = author.get("display_name", "")
            if name:
                authors.append(name)

        year = work.get("publication_year")

        doi = work.get("doi", "") or ""
        url = doi if doi.startswith("http") else work.get("id", "")

        pubs.append({
            "title": title,
            "abstract": abstract,
            "authors": authors,
            "year": year,
            "source": "OpenAlex",
            "url": url,
            "doi": doi,
            "relevance_score": 0.0,
        })

    return pubs


# ── ClinicalTrials.gov ─────────────────────────────────────────────────────

async def fetch_clinical_trials(
    disease: str,
    query: str = "",
    location: str = "",
    max_results: int = TRIALS_MAX,
) -> list[dict]:
    """Fetch trials with graceful location/intervention fallback."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        url = "https://clinicaltrials.gov/api/v2/studies"

        async def _try_fetch(params):
            all_trials = []
            for status in ["RECRUITING", "COMPLETED"]:
                p = {**params, "filter.overallStatus": status}
                try:
                    resp = await client.get(url, params=p)
                    resp.raise_for_status()
                    data = resp.json()
                    studies = data.get("studies", [])
                    all_trials.extend(_parse_trials(studies))
                except Exception as e:
                    print(f"[Trials] {status} failed: {e}")
            return all_trials

        base_params = {
            "query.cond": disease,
            "pageSize": min(max_results, 100),
            "format": "json",
        }
        if query:
            base_params["query.intr"] = query
        if location:
            base_params["query.locn"] = location

        trials = await _try_fetch(base_params)
        print(f"[Trials] Attempt 1 (full filters): {len(trials)} trials")

        if len(trials) < 3 and location:
            print(f"[Trials] Retrying without location filter ({location})")
            base_params.pop("query.locn", None)
            trials = await _try_fetch(base_params)
            print(f"[Trials] Attempt 2: {len(trials)} trials")

        if len(trials) < 3 and query:
            print(f"[Trials] Retrying without intervention filter")
            base_params.pop("query.intr", None)
            trials = await _try_fetch(base_params)
            print(f"[Trials] Attempt 3: {len(trials)} trials")

        return trials[:max_results]


def _parse_trials(studies: list[dict]) -> list[dict]:
    """Normalize ClinicalTrials.gov study objects."""
    trials = []
    for study in studies:
        try:
            protocol = study.get("protocolSection", {})
            id_module = protocol.get("identificationModule", {})
            status_module = protocol.get("statusModule", {})
            elig_module = protocol.get("eligibilityModule", {})
            contacts_module = protocol.get("contactsLocationsModule", {})
            cond_module = protocol.get("conditionsModule", {})
            interv_module = protocol.get("armsInterventionsModule", {})

            nct_id = id_module.get("nctId", "")
            title = id_module.get("briefTitle", "") or id_module.get("officialTitle", "")

            status = status_module.get("overallStatus", "")
            conditions = cond_module.get("conditions", [])

            interventions = []
            for interv in interv_module.get("interventions", []):
                name = interv.get("name", "")
                if name:
                    interventions.append(name)

            eligibility = elig_module.get("eligibilityCriteria", "")[:500]

            locations = []
            for loc in contacts_module.get("locations", [])[:5]:
                facility = loc.get("facility", "")
                city = loc.get("city", "")
                country = loc.get("country", "")
                loc_str = ", ".join(filter(None, [facility, city, country]))
                if loc_str:
                    locations.append(loc_str)

            contacts = []
            for contact in contacts_module.get("centralContacts", [])[:3]:
                name = contact.get("name", "")
                email = contact.get("email", "")
                if name:
                    contacts.append(f"{name} ({email})" if email else name)

            url = f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else ""

            trials.append({
                "title": title,
                "nct_id": nct_id,
                "status": status,
                "conditions": conditions,
                "interventions": interventions,
                "eligibility": eligibility,
                "locations": locations,
                "contacts": contacts,
                "url": url,
                "relevance_score": 0.0,
            })
        except Exception:
            continue

    return trials


# ── Parallel fetch all sources ──────────────────────────────────────────────

async def fetch_all_sources(
    queries: list[str],
    disease: str,
    location: str = "",
    prefer_recent: bool = True,
) -> tuple[list[dict], list[dict]]:
    """Run all retrieval agents truly in parallel.

    FIX v2: PubMed tasks now use global semaphore so they don't slam NCBI.
    OpenAlex and Trials run freely in parallel.
    """
    pub_tasks = []

    # IMPORTANT: Cap to 2 queries for PubMed to avoid rate limit cascade
    pubmed_queries = queries[:2]  # Use fewer queries for PubMed
    for q in pubmed_queries:
        pub_tasks.append(fetch_pubmed(q, sort_by_date=prefer_recent))

    # OpenAlex can handle more concurrent queries
    for q in queries:
        pub_tasks.append(fetch_openalex(q, sort_by_date=prefer_recent))

    primary_query = queries[0] if queries else disease
    trial_task = fetch_clinical_trials(disease, primary_query, location)

    all_results = await asyncio.gather(
        *pub_tasks, trial_task, return_exceptions=True
    )

    all_pubs = []
    for i, result in enumerate(all_results[:-1]):
        if isinstance(result, Exception):
            print(f"[Retrieval] Task {i} exception: {result}")
            continue
        all_pubs.extend(result)

    trials_result = all_results[-1]
    all_trials = [] if isinstance(trials_result, Exception) else trials_result

    pubmed_count = sum(1 for p in all_pubs if p.get("source") == "PubMed")
    openalex_count = sum(1 for p in all_pubs if p.get("source") == "OpenAlex")
    print(f"[Retrieval] Total: {pubmed_count} PubMed + {openalex_count} OpenAlex + {len(all_trials)} trials")

    return all_pubs, all_trials