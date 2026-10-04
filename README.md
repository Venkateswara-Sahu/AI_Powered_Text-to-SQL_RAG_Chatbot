---
title: F1InsightAI
emoji: 🏎️
colorFrom: red
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

# 🏎️ F1InsightAI — AI-Powered Formula 1 Text-to-SQL RAG Chatbot

A Text-to-SQL prototype that converts natural-language Formula 1 questions into SELECT queries over a documented 700,000+ records in 14 TiDB data tables. It combines a nine-node LangGraph workflow, FAISS schema retrieval, a Groq-hosted LLM, Flask, and Docker.

This was the Jan–May 2026 industry project for **TransOrg Analytics (Pickl.AI) × Lovely Professional University**. I led its technical implementation; the academic submission was completed as a group project.

[Live Hugging Face demo](https://huggingface.co/spaces/RiverStead/Text-to-SQL_RAG_Chatbot)

## Evaluation snapshot

| Measure | Result | Scope |
|---|---:|---|
| Historical SQL-question smoke checks | **15/18 (83.3%)** | Generated SQL, nonempty results and expected answer keywords; not reference-result equivalence or first-attempt accuracy |
| Historical retry success | **Not established** | The old benchmark read `steps`, while the API returns `agent_steps`; recorded zero counts cannot establish that retries were absent |
| Retrieval improvement | **No validated aggregate claimed** | Schema enrichment, system-table filtering and co-occurrence rules are implemented; historical MRR aggregation is unresolved |
| Database | **700,000+ rows** | 14 Formula 1 data tables in TiDB Cloud |

The [March 2026 artifact](tests/benchmark_results.json) remains unchanged. Its legacy accuracy, retry and timing fields must be interpreted using the [evaluation audit](docs/evaluation-audit.md). No fresh live model/database benchmark is claimed by the repair. Offline regression tests establish the corrected software behavior, not model accuracy or deployment readiness.

### Reproduce the software checks

```bash
python -m pip install -r requirements-test.txt
python -m pytest -q
node tests/metric_bar_check.cjs
```

To run a fresh smoke benchmark against your running API:

```bash
python tests/benchmark.py --api-url http://localhost:5000/api/chat
```

Each run creates a new JSON artifact under `artifacts/benchmarks/`, including the suite/code hashes, raw API responses, trace availability and observed retries. Unexercised retry rates are `null`. These checks still use answer keywords; independent reference SQL/results and a fixed database snapshot are needed before claiming execution accuracy.

### SQL execution boundary

Agent validation and database execution share a parsed MySQL query policy. It accepts one SELECT query, including supported CTE/UNION queries, and rejects writes, locking, session variables, executable comments, optimizer hints and unknown functions. An outer result cap is applied even when a literal or inner query contains `LIMIT`; the API returns the SQL actually executed.

With `MYSQL_SSL=true`, both pooled and fallback connections verify the certificate and hostname against `MYSQL_SSL_CA` (defaults to the certifi CA bundle). A TLS verification failure is not retried with verification disabled. The default query result cap is 50 rows; `SQL_MAX_ROWS` also bounds explicitly requested connector limits.

These are application controls. Database grants, query execution-time limits and live TLS connectivity have not been verified here. Conversation storage currently uses the same connection account and needs writes, so this project does not claim a separately enforced read-only database identity. Use restricted grants and isolate generated-query credentials before exposing sensitive data.

## ✨ Features

### Core
- **Natural Language to SQL** — Ask questions about F1 in plain English and inspect the generated SQL and results
- **RAG-Powered Schema Retrieval** — FAISS + sentence-transformers for context-aware SQL generation
- **LangGraph Agentic Pipeline** — Multi-step reasoning with classify → retrieve → generate → execute → reflect → answer
- **Error-Guided Retry Path** — The agent can attempt SQL correction after an execution error; successful correction is not guaranteed
- **SQL Execution Policy** — Shared parsed SELECT validation, side-effect checks and bounded result rows
- **Groq API** — Lightning-fast inference using GPT OSS 120B (free tier)
- **Retrieval Diagnostics** — Per-query reciprocal rank and table recall use generated SQL as a relevance proxy; answer checks measure result-value substring coverage

### User Experience
- **Responsive data interface** — Query results, telemetry, visualizations, and follow-up controls in one view
- **📊 Auto Chart Visualizations** — Bar, pie, and line charts auto-generated with distinct F1-themed colors
- **💡 AI Follow-up Suggestions** — LLM-generated follow-up questions appear as clickable pill chips
- **📌 Pin & Rename Chats** — Pin important conversations and rename them for easy reference
- **⋮ ChatGPT-Style Three-Dot Menu** — Hover to reveal dots, click for dropdown with Rename/Pin/Delete
- **🧠 Execution trace** — Collapsible view of application pipeline steps and evaluation signals
- **SQL Syntax Highlighting** — Color-coded keywords in a dark IDE-style card
- **CSV Export** — Download any query result table as a `.csv` file
- **SQL Download** — Download generated SQL as a `.sql` file
- **Responsive UI** — Desktop and mobile layouts for query results and charts
- **📊 Diagnostics Card** — Proxy definitions are visible; checks with no eligible values display “Not measured”
- **🐳 Docker Ready** — Dockerfile + Docker Compose for one-command deployment

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | Flask (Python) |
| Agent | LangGraph (multi-step reasoning) |
| LLM | Groq API (GPT OSS 120B) |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) |
| Vector Store | FAISS (Facebook AI Similarity Search) |
| Charts | Chart.js |
| Database | TiDB Cloud (F1 Database — 14 F1 tables, 700K+ rows) |
| Container | Docker + Docker Compose |

## 🏗️ Architecture

```
User Question
     │
     ▼
┌─────────────┐
│  Flask API  │  (app.py — /api/chat)
└──────┬──────┘
       │ + chat history (last 20 msgs)
       ▼
┌──────────────────────────────────────────────────────┐
│         LangGraph Agent (9-node state graph)         │
│                                                      │
│  ┌──────────┐                                        │
│  │ classify │─── "conversation" ──▶ direct_answer ─▶ END │
│  └────┬─────┘                                        │
│       │ "database"                                   │
│       ▼                                              │
│  ┌─────────────────┐                                 │
│  │ retrieve_schema │  RAG: FAISS top-7 + co-occurrence  │
│  └────────┬────────┘                                 │
│           ▼                                          │
│  ┌──────────────┐                                    │
│  │ generate_sql │  Groq LLM (GPT OSS 120B)          │
│  └──────┬───────┘                                    │
│         ▼                                            │
│  ┌─────────────┐                                     │
│  │ execute_sql │  TiDB Cloud (read-only)             │
│  └──────┬──────┘                                     │
│         ▼                                            │
│  ┌─────────┐    ❌ error                              │
│  │ reflect │───────────▶ retry_sql ──┐               │
│  └────┬────┘            (up to 2x)   │               │
│       │ ✅ ok       ◀────────────────┘               │
│       ▼                                              │
│  ┌─────────────────┐                                 │
│  │ generate_answer │  Natural language summary        │
│  └────────┬────────┘                                 │
│           ▼                                          │
│  ┌───────────────────┐                               │
│  │ generate_follow_  │  3 suggested questions         │
│  │       ups         │                               │
│  └────────┬──────────┘                               │
│           ▼                                          │
│          END                                         │
└──────────────────────────────────────────────────────┘
       │
       ▼
 Chat Response (Answer + SQL + Table + Chart + Follow-ups)
```

## 🚀 Setup Guide

### Prerequisites
- Python 3.9+
- TiDB Cloud account with F1 database ([tidbcloud.com](https://tidbcloud.com))
- Groq API key (free at [console.groq.com](https://console.groq.com))

### Step 1: Set up TiDB Cloud

1. Create a free TiDB Serverless cluster on [TiDB Cloud](https://tidbcloud.com)
2. Import the F1 database — you can use the [f1db dataset](https://github.com/f1db/f1db)
3. Note your connection details (host, port, user, password)

### Step 2: Install Python Dependencies

```bash
# Create a virtual environment (recommended)
python -m venv venv
venv\Scripts\activate   # Windows
# source venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt
```

### Step 3: Configure Environment

Copy `.env.example` to `.env` and fill in your TiDB Cloud credentials:

```env
MYSQL_HOST=gateway01.ap-southeast-1.prod.aws.tidbcloud.com
MYSQL_PORT=4000
MYSQL_USER=your_tidb_user
MYSQL_PASSWORD=your_tidb_password
MYSQL_DATABASE=f1db
MYSQL_SSL=true
# MYSQL_SSL_CA=/path/to/trusted-ca-bundle.pem  # optional custom CA
SQL_MAX_ROWS=500
GROQ_API_KEY=your_groq_api_key
```

### Step 4: Run the Application

```bash
python app.py
```

Visit **http://localhost:5000** in your browser.

### Alternative: Docker Deployment

1. **Ensure your `.env` file** has these values:
   ```env
   GROQ_API_KEY=your_groq_api_key
   MYSQL_PASSWORD=f1insight123
   MYSQL_DATABASE=f1db
   ```

2. **Build and start:**
   ```bash
   docker-compose up --build
   ```

Visit **http://localhost:5000**.

## 📁 Project Structure

```
Project/
├── app.py                    # Flask app — API endpoints + orchestration
├── config.py                 # Centralized config (loads .env)
├── requirements.txt          # Python dependencies
├── .env                      # Environment variables (not in git)
├── .env.example              # Template for environment setup
│
├── agent/
│   ├── __init__.py           # Module: LangGraph agentic SQL pipeline
│   ├── agent.py              # 9-node state graph (classify → retrieve → generate → execute → reflect → answer) + RAG metrics
│   └── tools.py              # Agent tools (schema retrieval, SQL execution, validation, faithfulness check)
│
├── database/
│   ├── __init__.py           # Module: MySQL/TiDB connection + chat storage
│   ├── connector.py          # Connection pool + retry logic + safe query execution
│   └── chat_store.py         # Server-side conversation CRUD (rename, pin, delete)
│
├── rag/
│   ├── __init__.py           # Module: FAISS vector index + schema retrieval
│   └── embeddings.py         # Schema embedding + FAISS retrieval + co-occurrence rules + semantic enrichment
│
├── llm/
│   ├── __init__.py           # Module: Groq API integration + SQL generation
│   ├── prompt_templates.py   # System prompts + few-shot examples + F1 domain knowledge
│   └── sql_generator.py      # Groq LLM calls — SQL gen, auto-retry, answer gen
│
├── templates/
│   └── index.html            # Browser interface for chat, results, and telemetry
│
├── static/
│   ├── css/styles.css        # Responsive visual styling
│   └── js/app.js             # Chat engine, bento renderer, chart rendering, three-dot menu, card tilt
│
├── Dockerfile                # Container build config
└── docker-compose.yml        # Multi-service orchestration
```

## 💬 Example Questions

- *"Who has the most race wins in F1 history?"*
- *"Compare Hamilton and Verstappen career stats"*
- *"Show the 2023 race calendar with circuits"*
- *"Which circuit has hosted the most races?"*
- *"What is the average pit stop duration by team?"*
- *"List all champions from 2000 to 2024"*
- *"Show lap time trends for the Monaco Grand Prix"*

## 🔑 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Serve chat UI |
| POST | `/api/chat` | Send a question, get SQL + results |
| GET | `/api/health` | Health check (DB + RAG + LLM status) |
| GET | `/api/stats` | Database statistics (tables, rows, columns, model) |
| GET | `/api/tables` | List all available tables |
| GET | `/api/conversations` | List all conversations |
| POST | `/api/conversations` | Create a new conversation |
| DELETE | `/api/conversations/<id>` | Delete a conversation |
| PATCH | `/api/conversations/<id>/rename` | Rename a conversation |
| PATCH | `/api/conversations/<id>/pin` | Pin/unpin a conversation |

## 📄 License

This project is for educational/academic purposes (capstone project).
