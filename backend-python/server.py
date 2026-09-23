# """Curalink FastAPI server.

# Provides REST endpoints for the React frontend and Node.js API gateway.
# Handles conversation management with MongoDB and the LangGraph pipeline.
# """

# from __future__ import annotations
# import json
# import os
# import time
# from contextlib import asynccontextmanager

# from dotenv import load_dotenv
# from fastapi import FastAPI, HTTPException
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi.responses import StreamingResponse
# from pydantic import BaseModel

# load_dotenv()

# # ── MongoDB setup ──────────────────────────────────────────────────────────

# from pymongo import MongoClient

# MONGODB_URI = os.getenv("MONGODB_URI", "")
# _db = None


# def get_db():
#     global _db
#     if _db is None and MONGODB_URI:
#         client = MongoClient(MONGODB_URI)
#         _db = client.curalink
#     return _db


# def get_conversation_history(session_id: str, limit: int = 10) -> list[dict]:
#     """Retrieve recent conversation history from MongoDB."""
#     db = get_db()
#     if db is None:
#         return []
#     try:
#         conv = db.conversations.find_one({"session_id": session_id})
#         if conv and "messages" in conv:
#             return conv["messages"][-limit:]
#     except Exception as e:
#         print(f"[DB] Failed to get history: {e}")
#     return []


# def save_conversation(session_id: str, user_msg: str, assistant_msg: str):
#     """Append messages to conversation history in MongoDB."""
#     db = get_db()
#     if db is None:
#         return
#     try:
#         db.conversations.update_one(
#             {"session_id": session_id},
#             {
#                 "$push": {
#                     "messages": {
#                         "$each": [
#                             {"role": "user", "content": user_msg},
#                             {"role": "assistant", "content": assistant_msg[:2000]},
#                         ]
#                     }
#                 },
#                 "$set": {"updated_at": time.time()},
#                 "$setOnInsert": {"created_at": time.time()},
#             },
#             upsert=True,
#         )
#     except Exception as e:
#         print(f"[DB] Failed to save: {e}")


# # ── Response cache ─────────────────────────────────────────────────────────

# _cache: dict[str, dict] = {}


# def cache_key(disease: str, message: str) -> str:
#     return f"{disease.lower().strip()}::{message.lower().strip()}"


# # ── Preload models on startup ─────────────────────────────────────────────

# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     """Preload the cross-encoder model on startup."""
#     print("[Startup] Preloading cross-encoder model...")
#     try:
#         from reranker import _get_cross_encoder
#         _get_cross_encoder()
#         print("[Startup] Cross-encoder loaded successfully")
#     except Exception as e:
#         print(f"[Startup] Cross-encoder load failed (will retry on first request): {e}")
#     yield
#     print("[Shutdown] Cleaning up...")


# # ── FastAPI app ────────────────────────────────────────────────────────────

# app = FastAPI(
#     title="Curalink API",
#     description="AI Medical Research Assistant - Agentic RAG Pipeline",
#     version="1.0.0",
#     lifespan=lifespan,
# )

# cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=cors_origins + ["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )


# # ── Request/Response models ────────────────────────────────────────────────

# class ChatRequest(BaseModel):
#     message: str
#     disease: str = ""
#     location: str = ""
#     session_id: str = "default"


# class ChatResponse(BaseModel):
#     content: str
#     publications: list[dict] = []
#     trials: list[dict] = []
#     sources_count: int = 0
#     processing_time: float = 0.0


# # ── Endpoints ──────────────────────────────────────────────────────────────

# @app.get("/health")
# async def health_check():
#     return {"status": "ok", "service": "curalink-pipeline"}


# @app.post("/chat", response_model=ChatResponse)
# async def chat(request: ChatRequest):
#     """Main chat endpoint - runs the full agentic RAG pipeline."""
#     start_time = time.time()

#     # Check cache
#     ck = cache_key(request.disease, request.message)
#     if ck in _cache:
#         cached = _cache[ck]
#         cached["processing_time"] = 0.1
#         return ChatResponse(**cached)

#     # Get conversation history
#     history = get_conversation_history(request.session_id)

#     # Build initial state
#     from pipeline import get_pipeline
#     pipeline = get_pipeline()

#     initial_state = {
#         "user_message": request.message,
#         "disease": request.disease,
#         "location": request.location,
#         "session_id": request.session_id,
#         "conversation_history": history,
#         "retry_count": 0,
#         "errors": [],
#     }

#     try:
#         # Run the LangGraph pipeline
#         result = await pipeline.ainvoke(initial_state)

#         response_data = result.get("response", {})
#         content = response_data.get("content", "I couldn't generate a response. Please try again.")
#         publications = response_data.get("publications", [])
#         trials = response_data.get("trials", [])
#         sources_count = response_data.get("sources_count", 0)

#         processing_time = time.time() - start_time

#         # Save to conversation history
#         save_conversation(request.session_id, request.message, content)

#         # Cache the response
#         result_dict = {
#             "content": content,
#             "publications": publications,
#             "trials": trials,
#             "sources_count": sources_count,
#         }
#         _cache[ck] = result_dict

#         return ChatResponse(
#             content=content,
#             publications=publications,
#             trials=trials,
#             sources_count=sources_count,
#             processing_time=processing_time,
#         )

#     except Exception as e:
#         processing_time = time.time() - start_time
#         print(f"[Chat] Pipeline error: {e}")
#         raise HTTPException(
#             status_code=500,
#             detail=f"Pipeline error: {str(e)}",
#         )


# @app.post("/chat/stream")
# async def chat_stream(request: ChatRequest):
#     """Streaming chat endpoint - emits stage events as pipeline progresses."""
#     async def event_generator():
#         start_time = time.time()
 
#         def emit(event_type: str, **data):
#             """Helper to format SSE events."""
#             payload = {"type": event_type, **data}
#             return f"data: {json.dumps(payload)}\n\n"
 
#         # Check cache first
#         ck = cache_key(request.disease, request.message)
#         if ck in _cache:
#             yield emit("stage", stage="cache_hit", message="Found cached response")
#             cached = _cache[ck]
#             yield emit(
#                 "response",
#                 content=cached["content"],
#                 publications=cached.get("publications", []),
#                 trials=cached.get("trials", []),
#                 sources_count=cached.get("sources_count", 0),
#                 processing_time=0.2,
#             )
#             yield "data: [DONE]\n\n"
#             return
 
#         yield emit("stage", stage="router", message="Understanding your query")
 
#         history = get_conversation_history(request.session_id)
 
#         # Import the pipeline nodes directly so we can stream between them
#         from pipeline import (
#             get_fast_llm, get_synthesis_llm,
#             router_node, retrieval_node, grader_node,
#             synthesis_node, reflection_node, casual_node,
#         )
 
#         state = {
#             "user_message": request.message,
#             "disease": request.disease,
#             "location": request.location,
#             "session_id": request.session_id,
#             "conversation_history": history,
#             "retry_count": 0,
#             "errors": [],
#         }
 
#         try:
#             # Stage 1: Router
#             state = await router_node(state)
#             query_type = state.get("query_type", "medical_query")
 
#             if query_type == "casual":
#                 yield emit("stage", stage="casual", message="Preparing response")
#                 state = await casual_node(state)
#             else:
#                 # Stage 2: Parallel retrieval
#                 expanded = state.get("expanded_queries", [])
#                 yield emit(
#                     "stage",
#                     stage="retrieval",
#                     message=f"Searching PubMed, OpenAlex, and ClinicalTrials.gov",
#                     detail=f"Expanded to {len(expanded)} queries"
#                 )
#                 state = await retrieval_node(state)
 
#                 pub_count = len(state.get("raw_publications", []))
#                 trial_count = len(state.get("raw_trials", []))
#                 yield emit(
#                     "stage",
#                     stage="retrieved",
#                     message=f"Found {pub_count} publications and {trial_count} trials",
#                 )
 
#                 # Stage 3: Grading + reranking
#                 yield emit(
#                     "stage",
#                     stage="grading",
#                     message="Deduplicating and ranking results",
#                     detail="BM25 pre-filter → cross-encoder reranking"
#                 )
#                 state = await grader_node(state)
 
#                 final_pubs = len(state.get("ranked_publications", []))
#                 final_trials = len(state.get("ranked_trials", []))
#                 yield emit(
#                     "stage",
#                     stage="ranked",
#                     message=f"Selected top {final_pubs} publications and {final_trials} trials",
#                 )
 
#                 # Stage 4: Synthesis
#                 yield emit(
#                     "stage",
#                     stage="synthesis",
#                     message="Synthesizing research insights",
#                     detail="Llama 3.3 70B"
#                 )
#                 state = await synthesis_node(state)
 
#                 # Stage 5: Reflection (usually skipped now)
#                 yield emit("stage", stage="validation", message="Validating citations")
#                 state = await reflection_node(state)
 
#                 # Possible retry
#                 if state.get("needs_retry") and state.get("retry_count", 0) < 2:
#                     yield emit(
#                         "stage",
#                         stage="retry",
#                         message="Refining response for better accuracy"
#                     )
#                     state = await synthesis_node(state)
#                     state = await reflection_node(state)
 
#             response_data = state.get("response", {})
#             processing_time = time.time() - start_time
 
#             # Final response
#             yield emit(
#                 "response",
#                 content=response_data.get("content", ""),
#                 publications=response_data.get("publications", []),
#                 trials=response_data.get("trials", []),
#                 sources_count=response_data.get("sources_count", 0),
#                 processing_time=processing_time,
#             )
 
#             # Save to cache and DB
#             save_conversation(
#                 request.session_id,
#                 request.message,
#                 response_data.get("content", ""),
#             )
#             _cache[ck] = {
#                 "content": response_data.get("content", ""),
#                 "publications": response_data.get("publications", []),
#                 "trials": response_data.get("trials", []),
#                 "sources_count": response_data.get("sources_count", 0),
#             }
 
#         except Exception as e:
#             print(f"[Stream] Pipeline error: {e}")
#             yield emit("error", message=str(e))
 
#         yield "data: [DONE]\n\n"
 
#     return StreamingResponse(
#         event_generator(),
#         media_type="text/event-stream",
#         headers={
#             "Cache-Control": "no-cache",
#             "Connection": "keep-alive",
#             "X-Accel-Buffering": "no",  # Disable nginx buffering if deployed
#         },
#     )


# @app.delete("/conversations/{session_id}")
# async def clear_conversation(session_id: str):
#     """Clear conversation history for a session."""
#     db = get_db()
#     if db is not None:
#         db.conversations.delete_one({"session_id": session_id})
#     # Clear relevant cache entries
#     keys_to_remove = [k for k in _cache if True]  # Clear all for simplicity
#     for k in keys_to_remove:
#         _cache.pop(k, None)
#     return {"status": "cleared"}


# # ── Run ────────────────────────────────────────────────────────────────────

# if __name__ == "__main__":
#     import uvicorn
#     host = os.getenv("HOST", "0.0.0.0")
#     port = int(os.getenv("PORT", "8000"))
#     uvicorn.run("server:app", host=host, port=port, reload=True)

# -------------------------------------------------------------------------------------

"""Curalink FastAPI server.

Provides REST endpoints for the React frontend and Node.js API gateway.
Handles conversation management with MongoDB and the LangGraph pipeline.

PATCHED v3: Added summary_node handling in /chat/stream
"""

from __future__ import annotations
import json
import os
import time
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

load_dotenv()

# ── MongoDB setup ──────────────────────────────────────────────────────────

from pymongo import MongoClient

MONGODB_URI = os.getenv("MONGODB_URI", "")
_db = None


def get_db():
    global _db
    if _db is None and MONGODB_URI:
        client = MongoClient(MONGODB_URI)
        _db = client.curalink
    return _db


def get_conversation_history(session_id: str, limit: int = 10) -> list[dict]:
    """Retrieve recent conversation history from MongoDB using Node.js format."""
    db = get_db()
    if db is None:
        return []
    try:
        cursor = db.messages.find({"session_id": session_id}).sort("created_at", 1)
        history = list(cursor)
        
        # Convert to expected format
        formatted = [{"role": msg.get("role", "user"), "content": msg.get("content", "")} for msg in history]
        
        # Node.js might have just inserted the current user query. Exclude it so it's not doubled.
        if formatted and formatted[-1]["role"] == "user":
            formatted = formatted[:-1]
            
        return formatted[-limit:]
    except Exception as e:
        print(f"[DB] Failed to get history: {e}")
    return []


def save_conversation(session_id: str, user_msg: str, assistant_msg: str):
    """Note: The Node.js API Gateway natively handles streaming DB insertions.
    We do not need to dual-save here in Python, as it causes schema mismatch."""
    pass


# ── Response cache ─────────────────────────────────────────────────────────

_cache: dict[str, dict] = {}


def cache_key(disease: str, message: str) -> str:
    return f"{disease.lower().strip()}::{message.lower().strip()}"


# ── Preload models on startup ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Preload the cross-encoder model on startup."""
    print("[Startup] Preloading cross-encoder model...")
    try:
        from reranker import _get_cross_encoder
        _get_cross_encoder()
        print("[Startup] Cross-encoder loaded successfully")
    except Exception as e:
        print(f"[Startup] Cross-encoder load failed (will retry on first request): {e}")
    yield
    print("[Shutdown] Cleaning up...")


# ── FastAPI app ────────────────────────────────────────────────────────────

app = FastAPI(
    title="Curalink API",
    description="AI Medical Research Assistant - Agentic RAG Pipeline",
    version="1.0.0",
    lifespan=lifespan,
)

cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins + ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request/Response models ────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    disease: str = ""
    location: str = ""
    session_id: str = "default"


class ChatResponse(BaseModel):
    content: str
    publications: list[dict] = []
    trials: list[dict] = []
    sources_count: int = 0
    processing_time: float = 0.0


# ── Endpoints ──────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "curalink-pipeline"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Main chat endpoint - runs the full agentic RAG pipeline."""
    start_time = time.time()

    # Check cache
    ck = cache_key(request.disease, request.message)
    if ck in _cache:
        cached = _cache[ck]
        cached["processing_time"] = 0.1
        return ChatResponse(**cached)

    # Get conversation history
    history = get_conversation_history(request.session_id)

    # Build initial state
    from pipeline import get_pipeline
    pipeline = get_pipeline()

    initial_state = {
        "user_message": request.message,
        "disease": request.disease,
        "location": request.location,
        "session_id": request.session_id,
        "conversation_history": history,
        "retry_count": 0,
        "errors": [],
    }

    try:
        # Run the LangGraph pipeline
        result = await pipeline.ainvoke(initial_state)

        response_data = result.get("response", {})
        content = response_data.get("content", "I couldn't generate a response. Please try again.")
        publications = response_data.get("publications", [])
        trials = response_data.get("trials", [])
        sources_count = response_data.get("sources_count", 0)

        processing_time = time.time() - start_time

        # Save to conversation history
        save_conversation(request.session_id, request.message, content)

        # Cache the response
        result_dict = {
            "content": content,
            "publications": publications,
            "trials": trials,
            "sources_count": sources_count,
        }
        _cache[ck] = result_dict

        return ChatResponse(
            content=content,
            publications=publications,
            trials=trials,
            sources_count=sources_count,
            processing_time=processing_time,
        )

    except Exception as e:
        processing_time = time.time() - start_time
        print(f"[Chat] Pipeline error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline error: {str(e)}",
        )


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Streaming chat endpoint - emits stage events as pipeline progresses.

    PATCHED v3: Handles summary_node routing for recap requests.
    """
    async def event_generator():
        start_time = time.time()

        def emit(event_type: str, **data):
            """Helper to format SSE events."""
            payload = {"type": event_type, **data}
            return f"data: {json.dumps(payload)}\n\n"

        # Check cache first
        ck = cache_key(request.disease, request.message)
        if ck in _cache:
            yield emit("stage", stage="cache_hit", message="Found cached response")
            cached = _cache[ck]
            yield emit(
                "response",
                content=cached["content"],
                publications=cached.get("publications", []),
                trials=cached.get("trials", []),
                sources_count=cached.get("sources_count", 0),
                processing_time=0.2,
            )
            yield "data: [DONE]\n\n"
            return

        yield emit("stage", stage="router", message="Understanding your query")

        history = get_conversation_history(request.session_id)

        # Import the pipeline nodes directly so we can stream between them
        from pipeline import (
            get_fast_llm, get_synthesis_llm,
            router_node, retrieval_node, grader_node,
            synthesis_node, reflection_node, casual_node,
            summary_node,
        )

        state = {
            "user_message": request.message,
            "disease": request.disease,
            "location": request.location,
            "session_id": request.session_id,
            "conversation_history": history,
            "retry_count": 0,
            "errors": [],
        }

        try:
            # Stage 1: Router
            state = await router_node(state)
            query_type = state.get("query_type", "medical_query")

            if query_type == "casual":
                yield emit("stage", stage="casual", message="Preparing response")
                state = await casual_node(state)

            elif query_type == "summary":
                # FIX: Handle summary requests — no RAG pipeline needed
                yield emit("stage", stage="synthesis", message="Summarizing conversation")
                state = await summary_node(state)

            else:
                # Stage 2: Parallel retrieval
                expanded = state.get("expanded_queries", [])
                yield emit(
                    "stage",
                    stage="retrieval",
                    message="Searching PubMed, OpenAlex, and ClinicalTrials.gov",
                    detail=f"Expanded to {len(expanded)} queries",
                )
                state = await retrieval_node(state)

                pub_count = len(state.get("raw_publications", []))
                trial_count = len(state.get("raw_trials", []))
                yield emit(
                    "stage",
                    stage="retrieved",
                    message=f"Found {pub_count} publications and {trial_count} trials",
                )

                # Stage 3: Grading + reranking
                yield emit(
                    "stage",
                    stage="grading",
                    message="Deduplicating and ranking results",
                    detail="BM25 pre-filter → cross-encoder reranking",
                )
                state = await grader_node(state)

                final_pubs = len(state.get("ranked_publications", []))
                final_trials = len(state.get("ranked_trials", []))
                yield emit(
                    "stage",
                    stage="ranked",
                    message=f"Selected top {final_pubs} publications and {final_trials} trials",
                )

                # Stage 4: Synthesis
                yield emit(
                    "stage",
                    stage="synthesis",
                    message="Synthesizing research insights",
                    detail="Llama 3.3 70B",
                )
                state = await synthesis_node(state)

                # Stage 5: Reflection
                yield emit("stage", stage="validation", message="Validating citations")
                state = await reflection_node(state)

                # Possible retry
                if state.get("needs_retry") and state.get("retry_count", 0) < 2:
                    yield emit(
                        "stage",
                        stage="retry",
                        message="Refining response for better accuracy",
                    )
                    state = await synthesis_node(state)
                    state = await reflection_node(state)

            response_data = state.get("response", {})
            processing_time = time.time() - start_time

            # Final response
            yield emit(
                "response",
                content=response_data.get("content", ""),
                publications=response_data.get("publications", []),
                trials=response_data.get("trials", []),
                sources_count=response_data.get("sources_count", 0),
                processing_time=processing_time,
            )

            # Save to cache and DB
            save_conversation(
                request.session_id,
                request.message,
                response_data.get("content", ""),
            )
            _cache[ck] = {
                "content": response_data.get("content", ""),
                "publications": response_data.get("publications", []),
                "trials": response_data.get("trials", []),
                "sources_count": response_data.get("sources_count", 0),
            }

        except Exception as e:
            print(f"[Stream] Pipeline error: {e}")
            yield emit("error", message=str(e))

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.delete("/conversations/{session_id}")
async def clear_conversation(session_id: str):
    """Clear conversation history for a session."""
    db = get_db()
    if db is not None:
        db.conversations.delete_one({"session_id": session_id})
    # Clear relevant cache entries
    keys_to_remove = [k for k in _cache if True]
    for k in keys_to_remove:
        _cache.pop(k, None)
    return {"status": "cleared"}


# ── Run ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("server:app", host=host, port=port, reload=True)