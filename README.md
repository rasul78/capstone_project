# Sentinel AI

> **Multi-Agent Corporate Knowledge Assistant with Custom MCP Servers**
> EPAM AI Capstone Project · v4.3 · May 2026

A production-credible enterprise AI assistant that answers questions about
company policies and Kazakhstani law through **six specialised agents**
cooperating in a deterministic LangGraph state machine, augmented by
**three custom MCP servers** that bridge to external HTTP data sources.

---

## At a glance

```
            ┌──────────┐    ┌──────────────┐
  Question  │ Planner  │ →  │  DocSearch   │ →  ┌────────┐
   ───────► │ 🧭        │    │ 📂 RAG       │    │ Legal  │ →  ┌──────────────┐
            └──────────┘    └──────────────┘    │ ⚖️ MCP  │    │ WebResearch  │
                                                └────────┘    │ 🌐 DDG       │
                                                              └──────────────┘
                                                                       │
                                ┌──────────┐    ┌────────────┐         │
  Answer    ◄────────────────── │ Critic   │ ◄─ │ Synthesis  │ ◄───────┘
                                │ 🔍 check  │    │ 🧠 LLM     │
                                └──────────┘    └────────────┘
```

Every step emits a Server-Sent Event — the chat UI shows the agents thinking
in real time.

---

## Agentic flow

| Agent | Responsibility |
|---|---|
| 🧭 **Planner** | Decomposes the question and decides which downstream agents to invoke |
| 📂 **DocSearch** | Hybrid RAG (pgvector + keyword + optional BGE rerank) over corporate docs |
| ⚖️ **Legal** | Calls 3 custom MCP servers — legal_rk, hr, docs — for authoritative data |
| 🌐 **WebResearch** | DuckDuckGo fallback when local KB is insufficient |
| 🧠 **Synthesis** | LLM cascade (Groq → Gemini → Claude → Ollama) builds the markdown answer |
| 🔍 **Critic** | Reviews the answer for hallucinations and missing citations |

The pipeline is **explicit**: each agent reads from and writes to a shared
LangGraph state object. There is no autonomous role-play between agents —
execution is deterministic and replayable.

---

## Three custom MCP servers

Following the EPAM expert's guidance — *"build custom MCP wrappers for
existing HTTP APIs, developed independently rather than configured in
orchestrators"* — Sentinel exposes 13 tools across 3 standalone MCP servers:

| Server | Port | Tools | Pattern |
|---|---|---|---|
| **legal_rk** | 8101 | `search_law`, `get_article`, `fetch_law_page`, `list_codes` | HTTP scraping bridge → mock fallback |
| **hr** | 8102 | `get_mrp`, `get_min_wage`, `calculate_vacation_days`, `calculate_severance`, `get_indexed_amount` | Computational tools + bridge |
| **docs** | 8103 | `search_documents`, `list_documents`, `get_document`, `get_kb_stats` | Self-bridge to own backend |

Every server implements the **MCP 2024-11-05 specification** over both
**stdio** (canonical transport) and **HTTP** (for debugging via Swagger UI).
JSON-RPC 2.0 is implemented from scratch — no SDK dependency.

---

## Tech stack

```
Frontend       :  React + Zustand + Recharts
Backend        :  Python 3.11 + FastAPI 0.111
Orchestration  :  LangGraph (state machine)
Vector store   :  PostgreSQL + pgvector
Embeddings     :  paraphrase-multilingual-MiniLM-L12-v2
Reranker       :  BAAI/bge-reranker-v2-m3  (optional, gated by .env)
MCP transport  :  JSON-RPC 2.0 over stdio + HTTP
LLM cascade    :  Groq Llama-3.3-70B → Gemini 2.0 Flash → Claude Haiku 4.5 → Ollama
Auth           :  bcrypt + JWT-style sessions in PostgreSQL
Cache          :  Redis with in-memory LRU fallback
Streaming      :  Server-Sent Events for per-agent progress
```

---

## Quick start

### Prerequisites

* Python 3.11+, Node.js 18+
* PostgreSQL 15+ with pgvector extension
* Optional: Redis, Ollama (local LLM fallback)
* A Groq API key for the primary LLM (free tier works)

### Install

```bash
# 1. Backend
cd backend
python -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Frontend
cd ../frontend
npm install

# 3. Environment
cd ../backend
cp .env.example .env
# Edit .env — add GROQ_API_KEY and Postgres credentials
```

### Run (5 terminals)

```bash
# Terminal 1 — legal_rk MCP server
cd backend && source venv/bin/activate
python -m mcp_servers.legal_rk.server --transport http --port 8101

# Terminal 2 — hr MCP server
cd backend && source venv/bin/activate
python -m mcp_servers.hr.server --transport http --port 8102

# Terminal 3 — docs MCP server
cd backend && source venv/bin/activate
python -m mcp_servers.docs.server --transport http --port 8103

# Terminal 4 — main backend (start AFTER the three MCP servers)
cd backend && source venv/bin/activate
uvicorn main:app --reload --port 8000

# Terminal 5 — frontend
cd frontend
npm start
```

Then open <http://localhost:3000> and log in with `demo / demo123`.

To see the **agentic pipeline in action**, click **🔬 Show agent pipeline**
above the chat input box, then ask a question — the six agents will appear
as a live timeline.

---

## Try it

After the system is running, ask:

| Question | Triggers |
|---|---|
| «Какой МРП в 2026 году?» | hr MCP → `get_mrp` |
| «Сколько дней отпуска у педагога?» | hr MCP → `calculate_vacation_days` |
| «Что говорит статья 84 ТК РК?» | legal_rk MCP → `get_article` |
| «Какая корпоративная политика по отпускам?» | DocSearch only |
| «Какой штраф за клевету в Казахстане?» | legal_rk MCP + Web research |

The UI shows which agents fired, which MCP tools were called, and which
LLM provider answered.

---

## Repository structure

```
Capstone project/
├── backend/
│   ├── main.py                       # FastAPI app, agent wiring
│   ├── chat_fast_v2.py               # Synthesis agent (non-streaming endpoint)
│   ├── stream_chat_v2.py             # Streaming endpoint with agent progress
│   ├── mcp_client.py                 # MCP registry & client
│   ├── mcp_integration.py            # Routing heuristics + arg extraction
│   ├── mcp_routes.py                 # /api/mcp/* status endpoints
│   ├── mcp_servers/                  # Three standalone MCP servers
│   │   ├── _common.py                # Custom JSON-RPC 2.0 / MCP 2024-11-05
│   │   ├── legal_rk/                 # Kazakhstan law bridge
│   │   ├── hr/                       # HR computations + MRP/MZP bridge
│   │   └── docs/                     # Sentinel knowledge base bridge
│   ├── agents/                       # ResearchAgent, WebAgent, SynthesisAgent
│   ├── tests/                        # 76 pytest tests, all passing
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── pages/DocsChatPage.js     # Chat UI with agent-progress toggle
│   │   ├── components/AgentProgress.js   # Live SSE timeline of the pipeline
│   │   ├── store/index.js            # Zustand state
│   │   └── ...
│   └── package.json
└── docs/
    ├── Executive_Summary.docx        # 3 pages, for review committee
    ├── Architecture_Blueprint.docx   # 11+ pages, technical reviewers
    └── Self_Review.docx              # 8 pages, engineering reflection
```

---

## Tests

A pytest suite covers the agentic pipeline, all three MCP servers, the
integration layer, and adversarial inputs (prompt injection, malformed PDFs,
LLM provider failures).

```bash
cd backend
pip install pytest pytest-asyncio pypdf
python -m pytest tests/ -v
```

Expected: **76 passed in ~3 seconds**.

The suite explicitly covers every scenario from the EPAM expert checklist:

| Scenario | Where |
|---|---|
| «загрузил doc → задал вопрос → получил релевантный ответ» | `test_failure_modes.py::TestHappyPath` |
| «спросил то чего нет → должен честно отказаться» | `test_failure_modes.py::TestHonestRefusal` |
| «подал кривой PDF» | `test_failure_modes.py::TestMalformedFileUploads` |
| «LLM API упал → fallback сработал» | `test_failure_modes.py::TestLlmFallback` |
| «prompt injection → не выполнил» | `test_security.py::TestPromptInjection` |

---

## Why these architectural choices

A side-by-side comparison of the three multi-agent frameworks against
Sentinel's actual requirements is in `docs/Self_Review.docx`. Summary:

| Property | LangGraph (chosen) | CrewAI | AutoGen |
|---|---|---|---|
| Execution model | Explicit state graph | Role-based, autonomous | Conversational |
| Determinism | High | Low | Medium |
| Auditability | First-class | Implicit | Per-message |
| Best for | Pipelines, RAG, audit | Brainstorming crews | Multi-LLM negotiation |
| **Fit for Sentinel** | ✓ | Overkill | Wrong shape |

> Predictable execution beats clever execution when an enterprise is going
> to read the audit log.

---

## Configuration (`.env`)

```bash
# Required
GROQ_API_KEY=gsk_...
DATABASE_URL=postgresql://user:pass@localhost:5432/sentinel

# Optional LLM fallbacks
GEMINI_API_KEY=
ANTHROPIC_API_KEY=

# Feature toggles
RERANKER_ENABLED=false              # BGE-reranker-v2-m3 is 2.27 GB
RERANKER_MODEL=BAAI/bge-reranker-v2-m3

# MCP server URLs (defaults shown)
MCP_LEGAL_URL=http://localhost:8101
MCP_HR_URL=http://localhost:8102
MCP_DOCS_URL=http://localhost:8103

# Optional integrations
REDIS_URL=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

---

## Deliverables

* `docs/Executive_Summary.docx` — 1-2 page overview for the review committee
* `docs/Architecture_Blueprint.docx` — detailed technical blueprint with diagrams
* `docs/Self_Review.docx` — engineering reflection: decisions, trade-offs, lessons learned
* `backend/tests/` — 76 pytest tests covering positive, negative, and adversarial scenarios
* Source code (this repository)
* Video demo — see submission file

---

## License

This project was developed as an EPAM AI Capstone submission and is provided
as-is for evaluation purposes.

---

**Author:** Rasul Abilmazhinov  ·  **Date:** May 2026  ·  **Version:** 4.3