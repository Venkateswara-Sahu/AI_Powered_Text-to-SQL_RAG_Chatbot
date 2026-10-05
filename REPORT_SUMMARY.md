# F1InsightAI — Project Summary Report

> October 2026 re-evaluation: **39/40 (97.5%) first-attempt; 39/40 (97.5%) final** on 40 independent reference-result contracts; dense MRR@7 **0.678 → 0.888**. See [current results](docs/evaluation/results.md). Historical measurements below are retained for context and are superseded as primary evidence.

**Project Title:** F1InsightAI — AI-Powered Formula 1 Text-to-SQL RAG Chatbot  
**Student:** Venkateswara Sahu (12204893)  
**Course:** Term 8 — Capstone Project  
**Date:** March 2026

---

## 1. Introduction & Problem Statement

F1InsightAI is an AI-powered chatbot that allows users to query a comprehensive Formula 1 database (1950–2024, 14 F1 tables, 700K+ rows) using plain English. The system converts natural language questions into SQL queries using Retrieval-Augmented Generation (RAG) and a multi-step agentic pipeline.

**Problem:** Querying structured databases requires SQL expertise, creating a barrier for non-technical users. Naive Text-to-SQL approaches that send the entire schema to an LLM suffer from token inefficiency, reduced accuracy, and no error recovery.

**Solution:** A RAG pipeline retrieves only the relevant table schemas for each question, combined with a LangGraph agent that supports intent classification, self-reflection, and automatic error correction.

---

## 2. Technology Stack

| Component | Technology |
|-----------|------------|
| Backend | Flask (Python) |
| Agent Framework | LangGraph (9-node state graph) |
| LLM | Groq API — GPT OSS 120B |
| Embeddings | Sentence-Transformers (all-MiniLM-L6-v2) |
| Vector Store | FAISS (Facebook AI Similarity Search) |
| Database | TiDB Cloud (MySQL-compatible, serverless) |
| Frontend | HTML/CSS/JS + particles.js + Chart.js |
| Deployment | Docker + Docker Compose |

---

## 3. System Architecture

The system follows a 3-layer architecture:

**Frontend** → "Kinetic Cockpit" cinematic dark UI with tsParticles background, mouse-following spotlight, telemetry grid overlay, 3D card tilt, glassmorphism cards, rotating conic border on search, and a bento-grid results layout.

**Flask API** → REST endpoints for chat, conversations (CRUD, pin, rename), health check, and database stats.

**LangGraph Agent** → A 9-node stateful pipeline:

1. **classify** — Determines if the question needs SQL or is conversational
2. **retrieve_schema** — RAG retrieves top-7 relevant table schemas from FAISS + co-occurrence rules inject related tables
3. **generate_sql** — LLM generates a SQL SELECT query using schema context + F1 domain knowledge
4. **execute_sql** — Executes policy-checked SELECT queries on TiDB Cloud
5. **reflect** — Validates results; routes to retry or answer
6. **retry_sql** — Feeds execution errors back to the LLM; the normal successful-generation path permits one correction attempt
7. **generate_answer** — LLM creates a natural language summary
8. **generate_follow_ups** — LLM suggests 3 related follow-up questions
9. **direct_answer** — Handles conversational queries without SQL

---

## 4. RAG Pipeline

The RAG (Retrieval-Augmented Generation) pipeline ensures the LLM receives only relevant schema context:

- **Indexing (startup):** All 14 F1 table schemas (excluding 2 system tables) are converted to rich text documents, embedded using all-MiniLM-L6-v2 (384-dim vectors), normalized, and stored in a FAISS IndexFlatIP.
- **Retrieval (per query):** The user's question is embedded, and FAISS performs a top-7 cosine similarity search. Co-occurrence rules then auto-inject related tables (e.g., `results` → `drivers`, `races` → `circuits`).
- **Augmentation:** The retrieved table descriptions are injected into the LLM system prompt alongside few-shot examples and F1 domain knowledge (team name changes, race name changes, circuit name mappings).

This approach narrows schema context; an independent SQL-accuracy improvement has not been established.

---

## 5. Key Features

- **Natural Language to SQL** with RAG-based schema retrieval
- **Auto-retry** with error feedback (agent self-corrects failed queries)
- **Multi-turn context** (last 20 messages for pronoun resolution and follow-ups)
- **Auto-generated charts** (bar, pie, line) with smart column filtering
- **Conversation management** — create, rename, pin, delete chats (server-side storage)
- **ChatGPT-style three-dot menu** — hover to reveal ⋮ dots, click for dropdown with Rename/Pin/Delete
- **Agent reasoning transparency** — collapsible accordion showing each pipeline step
- **SQL syntax highlighting** with copy and download buttons
- **CSV export** for query result tables
- **F1 domain knowledge** — European countries, team name history, race name changes, circuit name mappings
- **Live diagnostics** — Generated-SQL table proxies and result-value substring coverage, with unavailable scores explicitly labelled
- **Docker deployment** — one-command setup with Docker Compose

### Cinematic Visual Effects ("Kinetic Cockpit" Design)

- **Mouse-following spotlight** — 800px radial gradient tracking cursor movement
- **Telemetry grid overlay** — persistent 40×40px CSS grid with red lines at 2% opacity
- **Rotating conic border** — `@property`-animated glow effect on the search input
- **3D card tilt on hover** — `MutationObserver`-backed perspective transform on result cards
- **Animated hero title** — multi-stop gradient animation with `-webkit-background-clip: text`
- **tsParticles network** — F1-themed red/orange connected particle background
- **Responsive search dock** — 60% viewport width, adapts from centered hero to fixed bottom bar
- **Fixed status bar** — real-time connection, model, table count, and row count display

---

## 6. Evidence and Software Checks

The unchanged March 2026 artifact contains 20 questions, including 18 SQL
questions. **15/18 (83.3%)** SQL-question cases passed generation, nonempty-result
and answer-keyword smoke checks. This is not reference-result correctness or
first-attempt accuracy.

The old benchmark read the wrong retry-trace field and defaulted to 100%
success with no retry denominator. Its zero retry counts cannot establish
whether retries occurred. Its latency numerator also excluded exception times.

The repaired benchmark reads agent_steps, preserves raw responses and
suite/code hashes, measures all request durations and writes fresh artifacts
without replacing historical results. Empty denominators are null.
Offline regression tests verify the implementation; the separate October
reference-result evaluation is linked above. See [evaluation-audit.md](docs/evaluation-audit.md).

## 7. Retrieval and Answer Diagnostics

Per-query reciprocal rank uses the best retrieved SQL-referenced table.
Table extraction respects qualified names and scoped CTEs. Relevance still
comes from generated SQL, so these diagnostics are not independent retrieval
evaluation. The historical aggregate 0.12 to 0.25 to 0.67 is unresolved and
is not a current claim.

Answer checks measure substring coverage of eligible values from the first
five result rows. They do not establish semantic faithfulness; no eligible
values means not measured. The UI uses these narrower definitions.

## 8. Execution Boundary and Conclusion

A shared parsed SELECT policy rejects multiple statements and known
side-effect constructs, applies an outer result cap and returns the executed
query. TLS-enabled connections verify certificate and hostname.

Database permissions, server-side resource limits, authenticated conversation
access remain deployment requirements; the completed local-model evaluation is linked above.
This is an academic prototype with tested software contracts and explicitly
bounded historical evidence.
