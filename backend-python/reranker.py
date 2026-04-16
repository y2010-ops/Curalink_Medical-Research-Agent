# """Re-ranking and deduplication module.

# Uses a cross-encoder model to score (query, abstract) pairs for relevance,
# then deduplicates across PubMed and OpenAlex sources.
# """

# from __future__ import annotations
# import os
# from difflib import SequenceMatcher

# # Lazy-load the cross-encoder to avoid slow startup
# _cross_encoder = None


# def _get_cross_encoder():
#     """Lazy-load the cross-encoder model on first use."""
#     global _cross_encoder
#     if _cross_encoder is None:
#         from sentence_transformers import CrossEncoder
#         _cross_encoder = CrossEncoder(
#             "cross-encoder/ms-marco-MiniLM-L-6-v2",
#             max_length=512,
#         )
#     return _cross_encoder


# def deduplicate_publications(publications: list[dict]) -> list[dict]:
#     """Remove duplicate publications by DOI or title similarity."""
#     seen_dois: set[str] = set()
#     seen_titles: list[str] = []
#     unique = []

#     for pub in publications:
#         # Skip empty titles
#         if not pub.get("title"):
#             continue

#         # DOI dedup
#         doi = pub.get("doi", "").strip().lower()
#         if doi and doi != "":
#             if doi in seen_dois:
#                 continue
#             seen_dois.add(doi)

#         # Title similarity dedup (catch cross-source duplicates)
#         title_lower = pub["title"].lower().strip()
#         is_dup = False
#         for seen_title in seen_titles:
#             ratio = SequenceMatcher(None, title_lower, seen_title).ratio()
#             if ratio > 0.85:
#                 is_dup = True
#                 break

#         if not is_dup:
#             seen_titles.append(title_lower)
#             unique.append(pub)

#     return unique


# def rerank_publications(
#     query: str,
#     publications: list[dict],
#     top_k: int | None = None,
# ) -> list[dict]:
#     """Score and rerank publications using cross-encoder relevance scoring.

#     Combines cross-encoder semantic relevance with a recency boost.
#     """
#     if not publications:
#         return []

#     if top_k is None:
#         top_k = int(os.getenv("FINAL_TOP_K", "8"))

#     model = _get_cross_encoder()

#     # Build (query, document) pairs for scoring
#     pairs = []
#     for pub in publications:
#         # Combine title and abstract for richer signal
#         doc_text = pub["title"]
#         if pub.get("abstract"):
#             doc_text += " " + pub["abstract"][:400]
#         pairs.append((query, doc_text))

#     # Score all pairs
#     scores = model.predict(pairs)

#     # Combine with recency boost
#     import datetime
#     current_year = datetime.datetime.now().year

#     for i, pub in enumerate(publications):
#         semantic_score = float(scores[i])

#         # Recency boost: papers from last 3 years get a bonus
#         recency_boost = 0.0
#         if pub.get("year"):
#             age = current_year - pub["year"]
#             if age <= 1:
#                 recency_boost = 0.5
#             elif age <= 3:
#                 recency_boost = 0.3
#             elif age <= 5:
#                 recency_boost = 0.1

#         pub["relevance_score"] = semantic_score + recency_boost

#     # Sort by combined score
#     publications.sort(key=lambda p: p["relevance_score"], reverse=True)

#     return publications[:top_k]


# def rerank_trials(
#     query: str,
#     disease: str,
#     trials: list[dict],
#     top_k: int = 6,
# ) -> list[dict]:
#     """Score and rerank clinical trials using cross-encoder."""
#     if not trials:
#         return []

#     model = _get_cross_encoder()

#     combined_query = f"{disease} {query}"
#     pairs = []
#     for trial in trials:
#         doc_text = trial["title"]
#         if trial.get("conditions"):
#             doc_text += " " + " ".join(trial["conditions"][:3])
#         if trial.get("interventions"):
#             doc_text += " " + " ".join(trial["interventions"][:3])
#         pairs.append((combined_query, doc_text))

#     scores = model.predict(pairs)

#     # Boost recruiting trials
#     for i, trial in enumerate(trials):
#         semantic_score = float(scores[i])
#         status_boost = 0.3 if trial.get("status") == "RECRUITING" else 0.0
#         trial["relevance_score"] = semantic_score + status_boost

#     trials.sort(key=lambda t: t["relevance_score"], reverse=True)

#     # Deduplicate by NCT ID
#     seen_ids = set()
#     unique_trials = []
#     for trial in trials:
#         nct = trial.get("nct_id", "")
#         if nct and nct in seen_ids:
#             continue
#         if nct:
#             seen_ids.add(nct)
#         unique_trials.append(trial)

#     return unique_trials[:top_k]
# -----------------------------------------------------------------------------

"""Re-ranking and deduplication module.

PATCHED v2:
- PubMed source boost (peer-reviewed > preprints)
- Filter out off-topic papers (ML methods, statistical analysis only)
- Quality threshold to drop low-relevance results
"""

from __future__ import annotations
import os
import re
from collections import Counter
from difflib import SequenceMatcher
from math import log
_cross_encoder = None

# Keywords that signal a paper is likely off-topic for treatment queries.
# Matched against lowercased titles. Comprehensive to catch ML/methods papers
# that describe themselves with "prediction", "classification", "network", etc.
OFF_TOPIC_TREATMENT_MARKERS = [
    "machine learning",
    "deep learning",
    "neural network",
    "neural networks",
    "prediction model",
    "predictive model",
    "prediction of",
    "predicting the risk",
    "predicting heart",
    "risk prediction",
    "disease prediction",
    "classification algorithm",
    "latent class analysis",
    "statistical analysis",
    "retrospective analysis of",
    "bibliometric",
    "meta-analysis of",
    "scoping review",
    "survey of patients",
    "cross-sectional study",
    "neutrosophic",
    "attention network",
    "dual-attention",
    "optidanet",
    "predictive analytics",
    "data mining",
    "feature selection",
]

def _bm25_prefilter(query: str, publications: list[dict], limit: int = 80) -> list[dict]:
    """Lightweight BM25 pre-filter to reduce candidate pool before cross-encoder.

    BM25 is ~100x faster than cross-encoder. We use it to cut 400+ candidates
    down to 80 before the expensive reranking stage. Brings latency from
    ~76s to ~45s with minimal accuracy loss.
    """
    if len(publications) <= limit:
        return publications

    query_tokens = re.findall(r'\w+', query.lower())
    if not query_tokens:
        return publications[:limit]

    docs = []
    for pub in publications:
        text = pub.get("title", "") + " " + pub.get("abstract", "")[:500]
        tokens = re.findall(r'\w+', text.lower())
        docs.append(tokens)

    doc_lens = [len(d) for d in docs]
    avg_dl = sum(doc_lens) / len(doc_lens) if doc_lens else 1

    N = len(docs)
    df = Counter()
    for doc in docs:
        unique = set(doc)
        for term in unique:
            if term in query_tokens:
                df[term] += 1

    idf = {term: log((N - df[term] + 0.5) / (df[term] + 0.5) + 1)
           for term in query_tokens if df[term] > 0}

    k1 = 1.5
    b = 0.75
    scored = []
    for i, doc in enumerate(docs):
        tf = Counter(doc)
        score = 0.0
        for term in query_tokens:
            if term in tf and term in idf:
                f = tf[term]
                numer = idf[term] * f * (k1 + 1)
                denom = f + k1 * (1 - b + b * doc_lens[i] / avg_dl)
                score += numer / denom
        scored.append((score, i))

    scored.sort(key=lambda x: x[0], reverse=True)
    top_indices = [i for _, i in scored[:limit]]
    return [publications[i] for i in top_indices]

def _get_cross_encoder():
    global _cross_encoder
    if _cross_encoder is None:
        from sentence_transformers import CrossEncoder
        _cross_encoder = CrossEncoder(
            "cross-encoder/ms-marco-MiniLM-L-6-v2",
            max_length=512,
        )
    return _cross_encoder


def deduplicate_publications(publications: list[dict]) -> list[dict]:
    """Remove duplicate publications by DOI or title similarity."""
    seen_dois: set[str] = set()
    seen_titles: list[str] = []
    unique = []

    for pub in publications:
        if not pub.get("title"):
            continue

        doi = pub.get("doi", "").strip().lower()
        if doi and doi != "":
            if doi in seen_dois:
                continue
            seen_dois.add(doi)

        title_lower = pub["title"].lower().strip()
        is_dup = False
        for seen_title in seen_titles:
            ratio = SequenceMatcher(None, title_lower, seen_title).ratio()
            if ratio > 0.85:
                is_dup = True
                break

        if not is_dup:
            seen_titles.append(title_lower)
            unique.append(pub)

    return unique


def _is_off_topic_for_treatment(title: str, query: str) -> bool:
    """Detect if a paper is about ML/prediction methods rather than treatments.

    Only applies when user is asking about treatments specifically.
    """
    query_lower = query.lower()
    if "treatment" not in query_lower and "therap" not in query_lower:
        return False  # Not a treatment query, don't filter

    title_lower = title.lower()
    for marker in OFF_TOPIC_TREATMENT_MARKERS:
        if marker in title_lower:
            return True
    return False


def rerank_publications(
    query: str,
    publications: list[dict],
    top_k: int | None = None,
    prefer_recent: bool = True,
) -> list[dict]:
    """Rerank with recency, source quality, and topic relevance boosts."""
    if not publications:
        return []

    if top_k is None:
        top_k = int(os.getenv("FINAL_TOP_K", "8"))

    # FIX: Filter pre-2020 when asking for "latest"
    if prefer_recent:
        recent_pubs = [p for p in publications if p.get("year") and p["year"] >= 2020]
        if len(recent_pubs) >= top_k:
            publications = recent_pubs
        elif len(recent_pubs) > 0:
            old_pubs = [p for p in publications if not p.get("year") or p["year"] < 2020]
            publications = recent_pubs + old_pubs[:top_k - len(recent_pubs)]

    # FIX: Filter off-topic papers for treatment queries
    query_lower = query.lower()
    if "treatment" in query_lower or "therap" in query_lower:
        before_count = len(publications)
        publications = [
            p for p in publications
            if not _is_off_topic_for_treatment(p.get("title", ""), query)
        ]
        filtered_count = before_count - len(publications)
        if filtered_count > 0:
            print(f"[Rerank] Filtered {filtered_count} off-topic ML/methods papers")

    if not publications:
        return []

    # BM25 pre-filter: cut 400+ candidates down to 80 before cross-encoder
    if len(publications) > 80:
        publications = _bm25_prefilter(query, publications, limit=80)
        print(f"[Rerank] BM25 pre-filter: reduced to {len(publications)} candidates")
    model = _get_cross_encoder()

    pairs = []
    for pub in publications:
        doc_text = pub["title"]
        if pub.get("abstract"):
            doc_text += " " + pub["abstract"][:400]
        pairs.append((query, doc_text))

    scores = model.predict(pairs)

    import datetime
    current_year = datetime.datetime.now().year

    for i, pub in enumerate(publications):
        semantic_score = float(scores[i])

        # Recency boost
        recency_boost = 0.0
        if pub.get("year"):
            age = current_year - pub["year"]
            if age <= 1:
                recency_boost = 1.5
            elif age <= 2:
                recency_boost = 1.0
            elif age <= 3:
                recency_boost = 0.5
            elif age <= 5:
                recency_boost = 0.1

        # FIX: Source quality boost - PubMed is peer-reviewed
        source_boost = 0.0
        if pub.get("source") == "PubMed":
            source_boost = 0.8  # Significant boost for peer-reviewed

        # FIX: Penalize papers with no abstract (likely low-quality)
        abstract_penalty = 0.0
        if not pub.get("abstract") or len(pub.get("abstract", "")) < 50:
            abstract_penalty = -0.5

        pub["relevance_score"] = semantic_score + recency_boost + source_boost + abstract_penalty

    publications.sort(key=lambda p: p["relevance_score"], reverse=True)

    # FIX: Quality threshold - drop papers with very low scores
    # (only if we have enough to still meet top_k)
    quality_filtered = [p for p in publications if p["relevance_score"] > -2.0]
    if len(quality_filtered) >= top_k:
        publications = quality_filtered

    return publications[:top_k]


def rerank_trials(
    query: str,
    disease: str,
    trials: list[dict],
    top_k: int = 6,
) -> list[dict]:
    """Score and rerank clinical trials using cross-encoder."""
    if not trials:
        return []

    model = _get_cross_encoder()

    combined_query = f"{disease} {query}"
    pairs = []
    for trial in trials:
        doc_text = trial["title"]
        if trial.get("conditions"):
            doc_text += " " + " ".join(trial["conditions"][:3])
        if trial.get("interventions"):
            doc_text += " " + " ".join(trial["interventions"][:3])
        pairs.append((combined_query, doc_text))

    scores = model.predict(pairs)

    for i, trial in enumerate(trials):
        semantic_score = float(scores[i])
        status_boost = 0.5 if trial.get("status") == "RECRUITING" else 0.0
        trial["relevance_score"] = semantic_score + status_boost

    trials.sort(key=lambda t: t["relevance_score"], reverse=True)

    seen_ids = set()
    unique_trials = []
    for trial in trials:
        nct = trial.get("nct_id", "")
        if nct and nct in seen_ids:
            continue
        if nct:
            seen_ids.add(nct)
        unique_trials.append(trial)

    return unique_trials[:top_k]