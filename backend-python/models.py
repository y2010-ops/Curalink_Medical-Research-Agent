# """Pydantic models and LangGraph state definitions for the Curalink pipeline."""

# from __future__ import annotations
# from typing import TypedDict, Literal, Optional
# from pydantic import BaseModel, Field


# # ── Pydantic models for API responses ──────────────────────────────────────

# class Publication(BaseModel):
#     title: str
#     abstract: str = ""
#     authors: list[str] = Field(default_factory=list)
#     year: int | None = None
#     source: Literal["PubMed", "OpenAlex"] = "PubMed"
#     url: str = ""
#     doi: str = ""
#     relevance_score: float = 0.0


# class ClinicalTrial(BaseModel):
#     title: str
#     nct_id: str = ""
#     status: str = ""
#     conditions: list[str] = Field(default_factory=list)
#     interventions: list[str] = Field(default_factory=list)
#     eligibility: str = ""
#     locations: list[str] = Field(default_factory=list)
#     contacts: list[str] = Field(default_factory=list)
#     url: str = ""
#     relevance_score: float = 0.0


# class StructuredResponse(BaseModel):
#     condition_overview: str = ""
#     research_insights: str = ""
#     clinical_trials_summary: str = ""
#     publications: list[Publication] = Field(default_factory=list)
#     trials: list[ClinicalTrial] = Field(default_factory=list)
#     sources_count: int = 0


# class UserInput(BaseModel):
#     message: str
#     disease: str = ""
#     location: str = ""
#     session_id: str = "default"


# # ── LangGraph State ────────────────────────────────────────────────────────

# class AgentState(TypedDict, total=False):
#     # Input
#     user_message: str
#     disease: str
#     location: str
#     session_id: str
#     conversation_history: list[dict]

#     # Router output
#     query_type: Literal["medical_query", "follow_up", "casual"]
#     expanded_queries: list[str]

#     # Retrieval output
#     raw_publications: list[dict]
#     raw_trials: list[dict]

#     # Graded + ranked output
#     ranked_publications: list[dict]
#     ranked_trials: list[dict]

#     # Synthesis output
#     response: dict
#     needs_retry: bool
#     retry_count: int

#     # Error tracking
#     errors: list[str]

# -----------------------------------------------------------------

"""Pydantic models and LangGraph state definitions for the Curalink pipeline.

PATCHED: Added `prefer_recent` flag to AgentState for recency-aware retrieval.
"""

from __future__ import annotations
from typing import TypedDict, Literal
from pydantic import BaseModel, Field


class Publication(BaseModel):
    title: str
    abstract: str = ""
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    source: Literal["PubMed", "OpenAlex"] = "PubMed"
    url: str = ""
    doi: str = ""
    relevance_score: float = 0.0


class ClinicalTrial(BaseModel):
    title: str
    nct_id: str = ""
    status: str = ""
    conditions: list[str] = Field(default_factory=list)
    interventions: list[str] = Field(default_factory=list)
    eligibility: str = ""
    locations: list[str] = Field(default_factory=list)
    contacts: list[str] = Field(default_factory=list)
    url: str = ""
    relevance_score: float = 0.0


class StructuredResponse(BaseModel):
    condition_overview: str = ""
    research_insights: str = ""
    clinical_trials_summary: str = ""
    publications: list[Publication] = Field(default_factory=list)
    trials: list[ClinicalTrial] = Field(default_factory=list)
    sources_count: int = 0


class UserInput(BaseModel):
    message: str
    disease: str = ""
    location: str = ""
    session_id: str = "default"


class AgentState(TypedDict, total=False):
    # Input
    user_message: str
    disease: str
    location: str
    session_id: str
    conversation_history: list[dict]

    # Router output
    query_type: Literal["medical_query", "follow_up", "casual"]
    expanded_queries: list[str]
    prefer_recent: bool  # NEW: flag for recency-aware retrieval

    # Retrieval output
    raw_publications: list[dict]
    raw_trials: list[dict]

    # Graded + ranked output
    ranked_publications: list[dict]
    ranked_trials: list[dict]

    # Synthesis output
    response: dict
    needs_retry: bool
    retry_count: int

    # Error tracking
    errors: list[str]