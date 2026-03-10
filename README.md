# 🏎️ F1InsightAI — AI-Powered Formula 1 Text-to-SQL Chatbot

An AI-powered chatbot that converts natural language questions into SQL queries over a comprehensive Formula 1 database (1950–2024) hosted on **TiDB Cloud**. Built with Flask, a LangGraph agentic pipeline, Groq API (Llama 3.3 70B), and FAISS-based RAG for schema-aware SQL generation.

## ✨ Features

### Core
- **Natural Language to SQL** — Ask questions about F1 in plain English, get accurate SQL queries
- **LangGraph Agentic Pipeline** — Multi-step reasoning with automatic retries and error correction
- **RAG-Powered Schema Retrieval** — FAISS + sentence-transformers for context-aware SQL generation
- **Auto-Retry with Error Feedback** — If a query fails, the agent gets the error and automatically fixes the SQL
- **Read-Only SQL Enforcement** — Only SELECT queries are allowed; all write operations are blocked
- **Groq API** — Lightning-fast inference using Llama 3.3 70B (free tier)

### User Experience
- **ChatGPT-Style Conversations** — Full conversation history with new chat, switch, rename, pin, and delete
- **📊 Auto Chart Visualizations** — Bar, pie, and line charts auto-generated from query results using Chart.js
- **💡 AI Follow-up Suggestions** — LLM-generated follow-up questions appear as clickable chips after each answer
- **📌 Pin & Rename Chats** — Pin important conversations and rename them for easy reference
- **SQL Syntax Highlighting** — Color-coded keywords, functions, strings, and numbers
- **CSV Export** — Download any query result table as a `.csv` file
- **SQL Download** — Download generated SQL as a `.sql` file
- **Execution Time Stats** — See how long each query takes
- **Welcome Dashboard** — Live database stats (tables, rows, columns, model) + suggestion chips
- **Toast Notifications** — Non-intrusive feedback for copy, download, and errors
- **Premium Dark UI** — F1-themed design with glassmorphism, micro-animations, and depth effects
- **Responsive Design** — Works on desktop, tablet, and mobile
- **🐳 Docker Ready** — Dockerfile + Docker Compose for one-command deployment

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | Flask (Python) |
| Agent | LangGraph (multi-step reasoning) |
| LLM | Groq API (Llama 3.3 70B Versatile) |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) |
| Vector Store | FAISS (Facebook AI Similarity Search) |
| Charts | Chart.js |
| Database | TiDB Cloud (F1 Database — 16 tables, 700K+ rows) |
| Container | Docker + Docker Compose |

## 🏗️ Architecture

```
User Question
     │
     ▼
┌─────────────┐     ┌──────────────────┐
│  Flask API  │────▶│  RAG Retrieval   │
│  (app.py)   │     │  (FAISS + Schema │
└──────┬──────┘     │   Embeddings)    │
       │            └────────┬─────────┘
       │                     │ Top-K relevant schema
       ▼                     ▼
┌──────────────────────────────────┐
│  LangGraph Agent (Multi-Step)    │
│  Groq LLM (Llama 3.3 70B)       │
│  System Prompt + Schema Context  │
└──────────────┬───────────────────┘
               │ Generated SQL
               ▼
┌──────────────────────────┐
│   TiDB Cloud (F1 DB)     │
│   Read-Only Execution    │
└──────────────┬───────────┘
               │ Query Results
               ▼
┌──────────────────────────┐
│  LLM Answer Generation   │
│  (Natural Language)       │
└──────────────┬───────────┘
               │
               ▼
         Chat Response
  (Answer + SQL + Table + Chart)
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
│   ├── agent.py              # LangGraph agentic SQL pipeline
│   └── tools.py              # Agent tools (query, schema lookup, etc.)
│
├── database/
│   ├── connector.py          # MySQL connection pool + safe query execution
│   ├── chat_store.py         # Server-side conversation storage (rename, pin)
│   └── schema_dump.txt       # Database schema reference
│
├── rag/
│   └── embeddings.py         # FAISS vector index + schema embedding + retrieval
│
├── llm/
│   ├── prompt_templates.py   # System prompts + few-shot examples + schema
│   └── sql_generator.py      # Groq LLM — SQL gen, retry, answer gen
│
├── templates/
│   └── index.html            # Chat UI (F1-themed premium design)
│
├── static/
│   ├── css/styles.css        # Dark theme, glassmorphism, micro-animations
│   └── js/app.js             # Conversation engine + sidebar + exports
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
