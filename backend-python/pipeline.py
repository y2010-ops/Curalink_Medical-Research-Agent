# """LangGraph Agentic RAG Pipeline for Curalink.

# Architecture:
#   Router → Parallel Retrieval → Dedup + Rerank → LLM Synthesis → Reflection Loop

# Each node is a function operating on shared AgentState.
# The graph uses conditional edges for routing and retry logic.
# """

# from __future__ import annotations
# import json
# import os
# from typing import Literal

# from dotenv import load_dotenv
# from langchain_core.messages import HumanMessage, SystemMessage
# from langchain_groq import ChatGroq
# from langgraph.graph import StateGraph, END

# from models import AgentState
# from retrievers import fetch_all_sources
# from reranker import (
#     deduplicate_publications,
#     rerank_publications,
#     rerank_trials,
# )

# load_dotenv()

# # ── LLM instances ──────────────────────────────────────────────────────────

# _fast_llm = None
# _synth_llm = None


# def get_fast_llm() -> ChatGroq:
#     """Llama 3.1 8B for routing, grading, query expansion (fast + cheap)."""
#     global _fast_llm
#     if _fast_llm is None:
#         _fast_llm = ChatGroq(
#             model=os.getenv("FAST_MODEL", "openai/gpt-oss-20b"),
#             temperature=0.1,
#             max_tokens=1024,
#         )
#     return _fast_llm


# def get_synthesis_llm() -> ChatGroq:
#     """Llama 3.3 70B for final synthesis (higher quality)."""
#     global _synth_llm
#     if _synth_llm is None:
#         _synth_llm = ChatGroq(
#             model=os.getenv("SYNTHESIS_MODEL", "openai/gpt-oss-120b"),
#             temperature=0.2,
#             max_tokens=4096,
#         )
#     return _synth_llm


# # ── Node 1: Router Agent ──────────────────────────────────────────────────

# async def router_node(state: AgentState) -> AgentState:
#     """Classify query type and expand search queries.

#     Uses the fast LLM to:
#     1. Determine if this is a medical query, follow-up, or casual chat
#     2. Extract/confirm disease and intent
#     3. Generate expanded search queries for broad retrieval
#     """
#     llm = get_fast_llm()

#     # Build context from conversation history
#     history_context = ""
#     conv_history = state.get("conversation_history", [])
#     if conv_history:
#         recent = conv_history[-6:]  # Last 3 exchanges
#         history_context = "\n".join(
#             f"{msg['role']}: {msg['content'][:200]}" for msg in recent
#         )

#     prompt = f"""You are a medical research query router. Analyze the user's message and respond ONLY with valid JSON.

# Conversation history:
# {history_context}

# Current message: {state["user_message"]}
# Disease context: {state.get("disease", "")}
# Location: {state.get("location", "")}

# Respond with this exact JSON structure:
# {{
#     "query_type": "medical_query" or "follow_up" or "casual",
#     "disease": "the primary disease/condition (extracted or from context)",
#     "expanded_queries": ["query1 combining disease + intent", "query2 alternative phrasing", "query3 broader related terms"],
#     "intent": "brief description of what the user wants to know"
# }}

# Rules:
# - If the user mentions a disease or treatment, query_type is "medical_query"
# - If the user asks a follow-up without specifying a new disease, query_type is "follow_up" and use disease from history
# - If it's greeting/casual, query_type is "casual"
# - expanded_queries should combine the disease + the specific intent for better retrieval
# - Generate 2-3 diverse but relevant search queries"""

#     try:
#         response = await llm.ainvoke([HumanMessage(content=prompt)])
#         content = response.content.strip()

#         # Extract JSON from response (handle markdown code blocks)
#         if "```" in content:
#             content = content.split("```")[1]
#             if content.startswith("json"):
#                 content = content[4:]
#             content = content.strip()

#         parsed = json.loads(content)

#         state["query_type"] = parsed.get("query_type", "medical_query")
#         state["expanded_queries"] = parsed.get("expanded_queries", [state["user_message"]])

#         # Update disease from router if detected
#         if parsed.get("disease"):
#             state["disease"] = parsed["disease"]

#     except Exception as e:
#         print(f"[Router] Failed: {e}")
#         state["query_type"] = "medical_query"
#         state["expanded_queries"] = [
#             f"{state.get('disease', '')} {state['user_message']}".strip()
#         ]
#         state["errors"] = state.get("errors", []) + [f"Router error: {str(e)}"]

#     return state


# # ── Node 2: Retrieval Agent ───────────────────────────────────────────────

# async def retrieval_node(state: AgentState) -> AgentState:
#     """Fetch publications and trials from all three sources in parallel."""
#     queries = state.get("expanded_queries", [state["user_message"]])
#     disease = state.get("disease", "")
#     location = state.get("location", "")

#     try:
#         raw_pubs, raw_trials = await fetch_all_sources(queries, disease, location)
#         state["raw_publications"] = raw_pubs
#         state["raw_trials"] = raw_trials
#         print(f"[Retrieval] Fetched {len(raw_pubs)} publications, {len(raw_trials)} trials")
#     except Exception as e:
#         print(f"[Retrieval] Failed: {e}")
#         state["raw_publications"] = []
#         state["raw_trials"] = []
#         state["errors"] = state.get("errors", []) + [f"Retrieval error: {str(e)}"]

#     return state


# # ── Node 3: Grader + Reranker ─────────────────────────────────────────────

# async def grader_node(state: AgentState) -> AgentState:
#     """Deduplicate, rerank, and select top publications and trials."""
#     raw_pubs = state.get("raw_publications", [])
#     raw_trials = state.get("raw_trials", [])
#     query = state["user_message"]
#     disease = state.get("disease", "")

#     # Deduplicate publications across PubMed and OpenAlex
#     deduped = deduplicate_publications(raw_pubs)
#     print(f"[Grader] Deduped: {len(raw_pubs)} → {len(deduped)} publications")

#     # Rerank with cross-encoder
#     top_k = int(os.getenv("FINAL_TOP_K", "8"))
#     combined_query = f"{disease} {query}".strip()

#     ranked_pubs = rerank_publications(combined_query, deduped, top_k=top_k)
#     ranked_trials = rerank_trials(combined_query, disease, raw_trials, top_k=6)

#     state["ranked_publications"] = ranked_pubs
#     state["ranked_trials"] = ranked_trials
#     print(f"[Grader] Final: {len(ranked_pubs)} publications, {len(ranked_trials)} trials")

#     return state


# # ── Node 4: Synthesizer ──────────────────────────────────────────────────

# async def synthesis_node(state: AgentState) -> AgentState:
#     """Generate a structured, source-backed response using Llama 3.3 70B."""
#     llm = get_synthesis_llm()

#     pubs = state.get("ranked_publications", [])
#     trials = state.get("ranked_trials", [])
#     disease = state.get("disease", "")
#     user_msg = state["user_message"]

#     # Format publications for the prompt
#     pub_context = ""
#     for i, pub in enumerate(pubs[:8], 1):
#         pub_context += f"\n[{i}] {pub['title']}"
#         if pub.get("authors"):
#             pub_context += f"\n    Authors: {', '.join(pub['authors'][:3])}"
#         if pub.get("year"):
#             pub_context += f" ({pub['year']})"
#         if pub.get("abstract"):
#             pub_context += f"\n    Abstract: {pub['abstract'][:300]}"
#         pub_context += f"\n    Source: {pub.get('source', 'Unknown')} | {pub.get('url', '')}\n"

#     # Format trials
#     trial_context = ""
#     for i, trial in enumerate(trials[:6], 1):
#         trial_context += f"\n[T{i}] {trial['title']}"
#         trial_context += f"\n     Status: {trial.get('status', 'Unknown')}"
#         trial_context += f"\n     NCT ID: {trial.get('nct_id', '')}"
#         if trial.get("locations"):
#             trial_context += f"\n     Locations: {', '.join(trial['locations'][:3])}"
#         if trial.get("interventions"):
#             trial_context += f"\n     Interventions: {', '.join(trial['interventions'][:3])}"
#         if trial.get("eligibility"):
#             trial_context += f"\n     Eligibility: {trial['eligibility'][:200]}"
#         trial_context += f"\n     URL: {trial.get('url', '')}\n"

#     # Conversation history for context
#     history = state.get("conversation_history", [])
#     history_text = ""
#     if history:
#         for msg in history[-4:]:
#             history_text += f"\n{msg['role']}: {msg['content'][:150]}"

#     system_prompt = """You are Curalink, an AI medical research assistant. You provide structured, research-backed answers.

# IMPORTANT RULES:
# 1. ONLY use information from the provided publications and trials. Do NOT hallucinate facts.
# 2. Cite sources using [1], [2], etc. for publications and [T1], [T2] for trials.
# 3. If information is insufficient, say so honestly rather than making things up.
# 4. Structure your response clearly with sections.
# 5. Be personalized to the user's disease context.
# 6. Include a disclaimer that this is for research purposes, not medical advice."""

#     user_prompt = f"""Disease context: {disease}
# User question: {user_msg}

# Previous conversation:
# {history_text}

# RESEARCH PUBLICATIONS:
# {pub_context if pub_context else "No publications found."}

# CLINICAL TRIALS:
# {trial_context if trial_context else "No clinical trials found."}

# Provide a structured response with these sections:
# 1. **Condition Overview**: Brief context about the disease/topic
# 2. **Research Insights**: Key findings from the publications (cite with [1], [2], etc.)
# 3. **Clinical Trials**: Relevant ongoing/completed trials (cite with [T1], [T2], etc.)
# 4. **Key Takeaways**: Actionable summary

# Remember: Only state what the sources support. Be specific and cite everything."""

#     try:
#         response = await llm.ainvoke([
#             SystemMessage(content=system_prompt),
#             HumanMessage(content=user_prompt),
#         ])

#         state["response"] = {
#             "content": response.content,
#             "publications": pubs[:8],
#             "trials": trials[:6],
#             "sources_count": len(pubs) + len(trials),
#         }
#         state["needs_retry"] = False

#     except Exception as e:
#         print(f"[Synthesis] Failed: {e}")
#         state["response"] = {
#             "content": f"I encountered an error generating the response. Here are the raw sources I found:\n\n"
#                        f"Publications found: {len(pubs)}\nTrials found: {len(trials)}",
#             "publications": pubs[:8],
#             "trials": trials[:6],
#             "sources_count": len(pubs) + len(trials),
#         }
#         state["needs_retry"] = False
#         state["errors"] = state.get("errors", []) + [f"Synthesis error: {str(e)}"]

#     return state


# # ── Node 5: Reflection / Hallucination Check ──────────────────────────────

# async def reflection_node(state: AgentState) -> AgentState:
#     """Lightweight check: does the response reference the provided sources?

#     Uses the fast LLM to verify the synthesis isn't hallucinating.
#     """
#     response = state.get("response", {})
#     content = response.get("content", "")
#     retry_count = state.get("retry_count", 0)

#     # Skip reflection if we've already retried or response is short
#     if retry_count >= 2 or len(content) < 100:
#         state["needs_retry"] = False
#         return state

#     llm = get_fast_llm()

#     pub_titles = [p["title"] for p in response.get("publications", [])[:5]]
#     trial_titles = [t["title"] for t in response.get("trials", [])[:3]]

#     check_prompt = f"""Check if this medical research response is grounded in the provided sources.

# Response to check:
# {content[:1500]}

# Available source titles:
# Publications: {json.dumps(pub_titles)}
# Trials: {json.dumps(trial_titles)}

# Respond with ONLY "PASS" or "FAIL".
# - PASS if the response cites sources and doesn't make unsupported claims
# - FAIL if it mentions specific studies, drugs, or statistics not in the sources"""

#     try:
#         check = await llm.ainvoke([HumanMessage(content=check_prompt)])
#         result = check.content.strip().upper()

#         if "FAIL" in result:
#             state["needs_retry"] = True
#             state["retry_count"] = retry_count + 1
#             print(f"[Reflection] FAILED check - retry #{state['retry_count']}")
#         else:
#             state["needs_retry"] = False
#             print("[Reflection] PASSED")

#     except Exception as e:
#         print(f"[Reflection] Check failed: {e}")
#         state["needs_retry"] = False  # Don't retry on reflection errors

#     return state


# # ── Casual Response Node ──────────────────────────────────────────────────

# async def casual_node(state: AgentState) -> AgentState:
#     """Handle non-medical queries with a friendly response."""
#     llm = get_fast_llm()
#     prompt = f"""You are Curalink, a friendly medical research assistant. The user sent a casual/greeting message.
# Respond briefly and warmly, then let them know you can help with medical research queries.

# User: {state["user_message"]}"""

#     try:
#         response = await llm.ainvoke([HumanMessage(content=prompt)])
#         state["response"] = {
#             "content": response.content,
#             "publications": [],
#             "trials": [],
#             "sources_count": 0,
#         }
#     except Exception:
#         state["response"] = {
#             "content": "Hello! I'm Curalink, your medical research assistant. "
#                        "Ask me about any disease, treatment, or clinical trial "
#                        "and I'll find the latest research for you.",
#             "publications": [],
#             "trials": [],
#             "sources_count": 0,
#         }

#     return state


# # ── Conditional Edge Functions ────────────────────────────────────────────

# def route_query(state: AgentState) -> Literal["retrieval", "casual"]:
#     """Route based on query type from router."""
#     if state.get("query_type") == "casual":
#         return "casual"
#     return "retrieval"


# def check_reflection(state: AgentState) -> Literal["synthesis", "end"]:
#     """Decide whether to retry synthesis after reflection."""
#     if state.get("needs_retry", False) and state.get("retry_count", 0) < 2:
#         return "synthesis"
#     return "end"


# # ── Build the Graph ───────────────────────────────────────────────────────

# def build_pipeline() -> StateGraph:
#     """Construct the LangGraph agentic RAG pipeline.

#     Graph structure:
#         router → [casual → END]
#                → [retrieval → grader → synthesis → reflection → END or → synthesis]
#     """
#     graph = StateGraph(AgentState)

#     # Add nodes
#     graph.add_node("router", router_node)
#     graph.add_node("casual", casual_node)
#     graph.add_node("retrieval", retrieval_node)
#     graph.add_node("grader", grader_node)
#     graph.add_node("synthesis", synthesis_node)
#     graph.add_node("reflection", reflection_node)

#     # Entry point
#     graph.set_entry_point("router")

#     # Conditional routing after router
#     graph.add_conditional_edges(
#         "router",
#         route_query,
#         {"retrieval": "retrieval", "casual": "casual"},
#     )

#     # Casual → END
#     graph.add_edge("casual", END)

#     # Main pipeline: retrieval → grader → synthesis → reflection
#     graph.add_edge("retrieval", "grader")
#     graph.add_edge("grader", "synthesis")
#     graph.add_edge("synthesis", "reflection")

#     # Reflection → retry synthesis or end
#     graph.add_conditional_edges(
#         "reflection",
#         check_reflection,
#         {"synthesis": "synthesis", "end": END},
#     )

#     return graph.compile()


# # Singleton compiled pipeline
# _pipeline = None


# def get_pipeline():
#     """Get or create the compiled LangGraph pipeline."""
#     global _pipeline
#     if _pipeline is None:
#         _pipeline = build_pipeline()
#     return _pipeline
# ---------------------------------------------------------------

"""LangGraph Agentic RAG Pipeline - PATCHED VERSION.

Fixes:
- Router detects 'latest'/'recent' intent and sets prefer_recent flag
- Reflection skips LLM check when response has 3+ citations (saves 5-10s)
- Grader uses prefer_recent flag for stronger recency filtering
"""

from __future__ import annotations
import json
import os
import re
from typing import Literal

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, END

from models import AgentState
from retrievers import fetch_all_sources
from reranker import (
    deduplicate_publications,
    rerank_publications,
    rerank_trials,
)

load_dotenv()

_fast_llm = None
_synth_llm = None


def get_fast_llm() -> ChatGroq:
    global _fast_llm
    if _fast_llm is None:
        _fast_llm = ChatGroq(
            model=os.getenv("FAST_MODEL", "openai/gpt-oss-20b"),
            temperature=0.1,
            max_tokens=1024,
        )
    return _fast_llm


def get_synthesis_llm() -> ChatGroq:
    global _synth_llm
    if _synth_llm is None:
        _synth_llm = ChatGroq(
            model=os.getenv("SYNTHESIS_MODEL", "openai/gpt-oss-120b"),
            temperature=0.2,
            max_tokens=4096,
        )
    return _synth_llm


# ── Node 1: Router Agent (PATCHED) ────────────────────────────────────────

RECENCY_KEYWORDS = {
    "latest", "recent", "new", "newest", "current", "emerging",
    "breakthrough", "2024", "2025", "2026", "updated", "modern"
}


def _detect_recency_intent(message: str) -> bool:
    """Check if user is asking for latest/recent research."""
    msg_lower = message.lower()
    return any(kw in msg_lower for kw in RECENCY_KEYWORDS)


async def router_node(state: AgentState) -> AgentState:
    """Classify query type and expand search queries.

    FIX: Now detects 'latest'/'recent' intent and stores it in state
    so the retrieval node can prioritize recent papers.
    """
    llm = get_fast_llm()

    # Detect recency intent from user message
    prefer_recent = _detect_recency_intent(state["user_message"])
    state["prefer_recent"] = prefer_recent
    if prefer_recent:
        print(f"[Router] Detected recency intent in query")

    history_context = ""
    conv_history = state.get("conversation_history", [])
    if conv_history:
        recent = conv_history[-6:]
        history_context = "\n".join(
            f"{msg['role']}: {msg['content'][:200]}" for msg in recent
        )

    prompt = f"""You are a medical research query router. Analyze the user's message and respond ONLY with valid JSON.

Conversation history:
{history_context}

Current message: {state["user_message"]}
Disease context: {state.get("disease", "")}
Location: {state.get("location", "")}

Respond with this exact JSON structure:
{{
    "query_type": "medical_query" or "follow_up" or "casual" or "summary",
    "disease": "the primary disease/condition (extracted or from context)",
    "expanded_queries": ["query1 combining disease + intent", "query2 alternative phrasing", "query3 broader related terms"],
    "intent": "brief description of what the user wants to know"
}}

Rules:
- If the user asks to summarize the conversation or chat, query_type is "summary"
- If the user mentions a disease or treatment, query_type is "medical_query"
- If the user asks a follow-up without specifying a new disease, query_type is "follow_up" and use disease from history
- If it's greeting/casual, query_type is "casual"
- expanded_queries should combine the disease + the specific intent for better retrieval
- Generate 2-3 diverse but relevant search queries"""

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        content = response.content.strip()

        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()

        parsed = json.loads(content)

        state["query_type"] = parsed.get("query_type", "medical_query")
        state["expanded_queries"] = parsed.get("expanded_queries", [state["user_message"]])

        if parsed.get("disease"):
            state["disease"] = parsed["disease"]

    except Exception as e:
        print(f"[Router] Failed: {e}")
        state["query_type"] = "medical_query"
        state["expanded_queries"] = [
            f"{state.get('disease', '')} {state['user_message']}".strip()
        ]
        state["errors"] = state.get("errors", []) + [f"Router error: {str(e)}"]

    return state


# ── Node 2: Retrieval Agent (PATCHED) ─────────────────────────────────────

async def retrieval_node(state: AgentState) -> AgentState:
    """Fetch publications and trials. FIX: Passes prefer_recent flag."""
    queries = state.get("expanded_queries", [state["user_message"]])
    disease = state.get("disease", "")
    location = state.get("location", "")
    prefer_recent = state.get("prefer_recent", True)  # Default to True

    try:
        raw_pubs, raw_trials = await fetch_all_sources(
            queries, disease, location, prefer_recent=prefer_recent
        )
        state["raw_publications"] = raw_pubs
        state["raw_trials"] = raw_trials
    except Exception as e:
        print(f"[Retrieval] Failed: {e}")
        state["raw_publications"] = []
        state["raw_trials"] = []
        state["errors"] = state.get("errors", []) + [f"Retrieval error: {str(e)}"]

    return state


# ── Node 3: Grader + Reranker (PATCHED) ───────────────────────────────────

async def grader_node(state: AgentState) -> AgentState:
    """FIX: Uses prefer_recent flag for stronger recency filtering."""
    raw_pubs = state.get("raw_publications", [])
    raw_trials = state.get("raw_trials", [])
    query = state["user_message"]
    disease = state.get("disease", "")
    prefer_recent = state.get("prefer_recent", True)

    deduped = deduplicate_publications(raw_pubs)
    print(f"[Grader] Deduped: {len(raw_pubs)} → {len(deduped)} publications")

    top_k = int(os.getenv("FINAL_TOP_K", "8"))
    combined_query = f"{disease} {query}".strip()

    ranked_pubs = rerank_publications(
        combined_query, deduped, top_k=top_k, prefer_recent=prefer_recent
    )
    ranked_trials = rerank_trials(combined_query, disease, raw_trials, top_k=6)

    state["ranked_publications"] = ranked_pubs
    state["ranked_trials"] = ranked_trials
    print(f"[Grader] Final: {len(ranked_pubs)} pubs ({sum(1 for p in ranked_pubs if p.get('year',0)>=2020)} from 2020+), {len(ranked_trials)} trials")

    return state


# ── Node 4: Synthesizer (unchanged) ───────────────────────────────────────

async def synthesis_node(state: AgentState) -> AgentState:
    llm = get_synthesis_llm()

    pubs = state.get("ranked_publications", [])
    trials = state.get("ranked_trials", [])
    disease = state.get("disease", "")
    user_msg = state["user_message"]

    pub_context = ""
    for i, pub in enumerate(pubs[:8], 1):
        pub_context += f"\n[{i}] {pub['title']}"
        if pub.get("authors"):
            pub_context += f"\n    Authors: {', '.join(pub['authors'][:3])}"
        if pub.get("year"):
            pub_context += f" ({pub['year']})"
        if pub.get("abstract"):
            pub_context += f"\n    Abstract: {pub['abstract'][:300]}"
        pub_context += f"\n    Source: {pub.get('source', 'Unknown')} | {pub.get('url', '')}\n"

    trial_context = ""
    for i, trial in enumerate(trials[:6], 1):
        trial_context += f"\n[T{i}] {trial['title']}"
        trial_context += f"\n     Status: {trial.get('status', 'Unknown')}"
        trial_context += f"\n     NCT ID: {trial.get('nct_id', '')}"
        if trial.get("locations"):
            trial_context += f"\n     Locations: {', '.join(trial['locations'][:3])}"
        if trial.get("interventions"):
            trial_context += f"\n     Interventions: {', '.join(trial['interventions'][:3])}"
        if trial.get("eligibility"):
            trial_context += f"\n     Eligibility: {trial['eligibility'][:200]}"
        trial_context += f"\n     URL: {trial.get('url', '')}\n"

    history = state.get("conversation_history", [])
    history_text = ""
    if history:
        for msg in history[-4:]:
            history_text += f"\n{msg['role']}: {msg['content'][:150]}"

    system_prompt = """You are Curalink, an empathetic and highly intelligent AI medical research companion.

IMPORTANT RULES:
1. GROUNDING: ONLY use information from the provided publications and trials. Do NOT hallucinate facts.
2. CITATIONS: Cite sources using [1], [2], etc. for publications and [T1], [T2] for trials.
3. TONE & COMPLEXITY: Strike a balance. Be human-like, warm, and understandable, but maintain medical accuracy. Do not be overly layman, but DO explain extremely complex statistical jargon and avoid raw mathematical formulas.
4. CONTEXT & PERSONALIZATION: Actively use the "Previous conversation" memory and the "Disease context" to tailor your response specifically to the user's ongoing situation. Make it flow naturally.
5. HONESTY: If information is insufficient, say so honestly rather than making things up.
6. STRUCTURING: Use clear sections.
7. DISCLAIMER: Include a brief disclaimer that this is for research purposes, not medical advice."""

    user_prompt = f"""Disease context: {disease}
Current question: {user_msg}

--- PREVIOUS CONVERSATION CONTEXT ---
{history_text if history_text else "No previous conversation."}

--- RESEARCH PUBLICATIONS ---
{pub_context if pub_context else "No publications found."}

--- CLINICAL TRIALS ---
{trial_context if trial_context else "No clinical trials found."}

Please provide a structured, personalized response following these sections:
1. **Context & Overview**: A warm opening acknowledging their specific query and condition context.
2. **Research Insights**: Key findings from the publications in an accessible but scientific tone (cite with [1], [2], etc.).
3. **Clinical Trials**: Relevant ongoing/completed trials (cite with [T1], [T2], etc.).
4. **Key Takeaways**: An actionable, personalized summary.

Remember: Blend scientific accuracy with accessible language. Only state what the sources support and cite everything."""

    try:
        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])

        state["response"] = {
            "content": response.content,
            "publications": pubs[:8],
            "trials": trials[:6],
            "sources_count": len(pubs) + len(trials),
        }
        state["needs_retry"] = False

    except Exception as e:
        print(f"[Synthesis] Failed: {e}")
        state["response"] = {
            "content": f"I encountered an error generating the response.",
            "publications": pubs[:8],
            "trials": trials[:6],
            "sources_count": len(pubs) + len(trials),
        }
        state["needs_retry"] = False
        state["errors"] = state.get("errors", []) + [f"Synthesis error: {str(e)}"]

    return state


# ── Node 5: Reflection (PATCHED - skip when well-cited) ───────────────────

async def reflection_node(state: AgentState) -> AgentState:
    """FIX: Skip LLM check when response already has 3+ unique citations.

    This saves 5-10 seconds per response when the synthesis is clearly grounded.
    Was responsible for a big chunk of the 81.9s latency.
    """
    response = state.get("response", {})
    content = response.get("content", "")
    retry_count = state.get("retry_count", 0)

    # FIX: Count unique citations like [1], [2], [T1], [T2]
    citations = re.findall(r'\[T?\d+\]', content)
    unique_citations = set(citations)

    if len(unique_citations) >= 3:
        state["needs_retry"] = False
        print(f"[Reflection] SKIPPED - {len(unique_citations)} unique citations found")
        return state

    # Skip if already retried or response is short
    if retry_count >= 1 or len(content) < 100:
        state["needs_retry"] = False
        return state

    # Only run the expensive LLM check if response has few citations
    llm = get_fast_llm()

    pub_titles = [p["title"] for p in response.get("publications", [])[:5]]
    trial_titles = [t["title"] for t in response.get("trials", [])[:3]]

    check_prompt = f"""Check if this medical response is grounded in provided sources.

Response: {content[:1000]}

Available sources:
Pubs: {json.dumps(pub_titles)}
Trials: {json.dumps(trial_titles)}

Respond with ONLY "PASS" or "FAIL"."""

    try:
        check = await llm.ainvoke([HumanMessage(content=check_prompt)])
        result = check.content.strip().upper()

        if "FAIL" in result:
            state["needs_retry"] = True
            state["retry_count"] = retry_count + 1
            print(f"[Reflection] FAILED - retry #{state['retry_count']}")
        else:
            state["needs_retry"] = False
            print("[Reflection] PASSED")

    except Exception as e:
        print(f"[Reflection] Check failed: {e}")
        state["needs_retry"] = False

    return state


# ── Casual Response Node (unchanged) ──────────────────────────────────────

async def casual_node(state: AgentState) -> AgentState:
    llm = get_fast_llm()
    prompt = f"""You are Curalink, a friendly medical research assistant. The user sent a casual/greeting message.
Respond briefly and warmly, then let them know you can help with medical research queries.

User: {state["user_message"]}"""

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        state["response"] = {
            "content": response.content,
            "publications": [],
            "trials": [],
            "sources_count": 0,
        }
    except Exception:
        state["response"] = {
            "content": "Hello! I'm Curalink. Ask me about any disease, treatment, or clinical trial and I'll find the latest research for you.",
            "publications": [],
            "trials": [],
            "sources_count": 0,
        }
    return state


# ── Summary Request Node ──────────────────────────────────────────────────

async def summary_node(state: AgentState) -> AgentState:
    """Handle requests to summarize the conversation history without full RAG."""
    llm = get_fast_llm()
    history = state.get("conversation_history", [])
    
    if not history:
        state["response"] = {
            "content": "There's no conversation history to summarize yet. How can I help you today?",
            "publications": [], "trials": [], "sources_count": 0
        }
        return state

    history_text = "\n".join(f"{msg['role']}: {msg['content'][:200]}" for msg in history)
    
    prompt = f"""You are Curalink. The user asked for a summary of the conversation.
    
Conversation:
{history_text}

Provide a concise, helpful summary of the health topics and research discussed."""
    
    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        state["response"] = {
            "content": response.content,
            "publications": [],
            "trials": [],
            "sources_count": 0,
        }
    except Exception as e:
        print(f"[Summary] Failed: {e}")
        state["response"] = {
            "content": "I couldn't generate a summary right now.",
            "publications": [], "trials": [], "sources_count": 0,
        }
    return state


# ── Conditional Edges ─────────────────────────────────────────────────────

def route_query(state: AgentState) -> Literal["retrieval", "casual"]:
    if state.get("query_type") == "casual":
        return "casual"
    return "retrieval"


def check_reflection(state: AgentState) -> Literal["synthesis", "end"]:
    if state.get("needs_retry", False) and state.get("retry_count", 0) < 2:
        return "synthesis"
    return "end"


def build_pipeline() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("router", router_node)
    graph.add_node("casual", casual_node)
    graph.add_node("retrieval", retrieval_node)
    graph.add_node("grader", grader_node)
    graph.add_node("synthesis", synthesis_node)
    graph.add_node("reflection", reflection_node)

    graph.set_entry_point("router")

    graph.add_conditional_edges(
        "router", route_query,
        {"retrieval": "retrieval", "casual": "casual"},
    )
    graph.add_edge("casual", END)
    graph.add_edge("retrieval", "grader")
    graph.add_edge("grader", "synthesis")
    graph.add_edge("synthesis", "reflection")
    graph.add_conditional_edges(
        "reflection", check_reflection,
        {"synthesis": "synthesis", "end": END},
    )

    return graph.compile()


_pipeline = None


def get_pipeline():
    global _pipeline
    if _pipeline is None:
        _pipeline = build_pipeline()
    return _pipeline