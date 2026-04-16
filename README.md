---
title: Medical Research Backend
emoji: ⚕️
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
---

# Curalink — AI Medical Research Assistant

An **agentic RAG** (Retrieval-Augmented Generation) system that fetches, ranks, and synthesizes medical research from PubMed, OpenAlex, and ClinicalTrials.gov using a LangGraph pipeline powered by open-source LLMs via Groq.

## Architecture

```
React (Vite + Tailwind)
        ↓
Node.js / Express API Gateway  ←→  MongoDB Atlas
        ↓
Python FastAPI + LangGraph Pipeline
        ↓
┌─────────────────────────────────────────┐
│  LangGraph Agentic Orchestrator         │
│                                         │
│  Router Agent (Llama 3.1 8B)            │
│      ↓                                  │
│  Parallel Retrieval Agents              │
│  ├── PubMed (50-100 results)            │
│  ├── OpenAlex (50-100 results)          │
│  └── ClinicalTrials.gov (20-50 results) │
│      ↓                                  │
│  Grader + Cross-Encoder Reranker        │
│  (ms-marco-MiniLM-L-6-v2)              │
│      ↓                                  │
│  Synthesizer (Llama 3.3 70B)            │
│      ↓                                  │
│  Reflection Loop (hallucination check)  │
└─────────────────────────────────────────┘
```

## Key Design Decisions

| Decision | Reasoning |
|----------|-----------|
| **LangGraph** over basic chain | Cyclic graph with conditional edges enables retry loops, query rewriting, and self-correction |
| **Groq + Llama 3.3 70B** | Open-source model with fast inference. ~315 tokens/sec. Free tier sufficient for demos |
| **Two-model strategy** | 8B for routing/grading (fast, cheap), 70B for synthesis (quality where it matters) |
| **Cross-encoder reranking** | Provably better relevance scoring than keyword-only. Runs on CPU |
| **Real-time retrieval** | Medical data changes rapidly. No stale embeddings. Fresh from source APIs |
| **Parallel retrieval** | All 3 sources hit simultaneously via asyncio. User doesn't wait for sequential calls |
| **Reflection loop** | Post-synthesis hallucination check with max 2 retries. Catches unsupported claims |

## Tech Stack

- **Frontend**: React 18, Vite, Tailwind CSS, lucide-react, react-markdown
- **API Gateway**: Node.js, Express, MongoDB driver
- **AI Pipeline**: Python, FastAPI, LangGraph, LangChain-Groq
- **Reranking**: sentence-transformers (cross-encoder/ms-marco-MiniLM-L-6-v2)
- **LLMs**: Llama 3.3 70B (synthesis), Llama 3.1 8B (routing/grading) via Groq
- **Database**: MongoDB Atlas (free tier)
- **Data Sources**: PubMed API, OpenAlex API, ClinicalTrials.gov API v2

## Quick Start (Local Development)

### Prerequisites
- Node.js 18+
- Python 3.10+
- Groq API key (free at https://console.groq.com)
- MongoDB Atlas account (free tier at https://www.mongodb.com/atlas)

### 1. Clone and setup environment

```bash
# Python backend
cd backend-python
cp .env.example .env
# Edit .env with your GROQ_API_KEY and MONGODB_URI
pip install -r requirements.txt

# Node.js gateway
cd ../backend-node
cp .env.example .env
npm install

# React frontend
cd ../frontend
npm install
```

### 2. Start all services

```bash
# Terminal 1: Python pipeline (port 8000)
cd backend-python
python server.py

# Terminal 2: Node.js gateway (port 3001)
cd backend-node
npm run dev

# Terminal 3: React frontend (port 5173)
cd frontend
npm run dev
```

### 3. Open http://localhost:5173

## Deployment (Railway + Vercel)

### Python Backend (Railway)
1. Create a new Railway project
2. Deploy from `backend-python/` directory
3. Set environment variables: `GROQ_API_KEY`, `MONGODB_URI`, `CORS_ORIGINS`
4. Note the deployment URL

### Node.js Gateway (Railway)
1. Add a new service in the same Railway project
2. Deploy from `backend-node/` directory
3. Set `PYTHON_API_URL` to the Python service's internal Railway URL
4. Set `MONGODB_URI`

### React Frontend (Vercel)
1. Import the `frontend/` directory
2. Set `VITE_API_URL` to the Node.js service's public URL + `/api`
3. Deploy

## Example Queries

- "Latest treatment for lung cancer"
- "Clinical trials for diabetes in Toronto"
- "Deep brain stimulation for Parkinson's disease"
- "Recent studies on Alzheimer's immunotherapy"
- Follow-up: "Can I take Vitamin D with this treatment?"

## Pipeline Details

### Retrieval Strategy (Depth-First)
1. Router expands user query into 2-3 search variations
2. Each variation hits PubMed AND OpenAlex simultaneously
3. ClinicalTrials.gov is queried with disease + location filters
4. Total candidate pool: 150-300 results
5. Deduplication removes cross-source duplicates (DOI + title similarity)
6. Cross-encoder scores all candidates against the original query
7. Final output: top 6-8 publications + top 4-6 trials

### Context Awareness
- Conversation history stored in MongoDB per session
- Follow-up questions inject previous disease context automatically
- Router agent detects follow-ups vs new queries

### Hallucination Mitigation
- LLM receives ONLY retrieved source text (no parametric knowledge)
- Strict citation requirements in system prompt ([1], [2], [T1], [T2])
- Reflection node validates that claims reference provided sources
- Up to 2 automatic retries if hallucination check fails

## License

MIT
