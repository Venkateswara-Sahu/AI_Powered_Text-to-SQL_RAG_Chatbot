# 🤖 NorthwindAI — AI-Powered Text-to-SQL RAG Chatbot

An AI-powered chatbot that converts natural language questions into SQL queries for the Northwind database. Built with Flask, Groq API (Llama 3.3 70B), and a FAISS-based RAG pipeline for accurate, schema-aware SQL generation.

## ✨ Features

### Core
- **Natural Language to SQL** — Ask questions in plain English, get accurate SQL queries
- **RAG-Powered Schema Retrieval** — FAISS + sentence-transformers for context-aware SQL generation
- **Auto-Retry with Error Feedback** — If a query fails, the LLM gets the error and automatically fixes the SQL
- **Read-Only SQL Enforcement** — Only SELECT queries are allowed; all write operations are blocked
- **Groq API** — Lightning-fast inference using Llama 3.3 70B (free tier)

### User Experience
- **ChatGPT-Style Conversations** — Full conversation history with new chat, switch, delete, and clear all
- **📊 Auto Chart Visualizations** — Bar, pie, and line charts auto-generated from query results using Chart.js
- **💡 AI Follow-up Suggestions** — LLM-generated follow-up questions appear as clickable chips after each answer
- **Dark / Light Mode** — Toggle with persistence via localStorage
- **SQL Syntax Highlighting** — Color-coded keywords, functions, strings, and numbers
- **CSV Export** — Download any query result table as a `.csv` file
- **SQL Download** — Download generated SQL as a `.sql` file
- **Execution Time Stats** — See how long each query takes
- **Welcome Dashboard** — Live database stats (tables, rows, columns, model) + suggestion chips
- **Toast Notifications** — Non-intrusive feedback for copy, download, and errors
- **Responsive Design** — Works on desktop, tablet, and mobile
- **🐳 Docker Ready** — Dockerfile + Docker Compose for one-command deployment

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | Flask (Python) |
| LLM | Groq API (Llama 3.3 70B Versatile) |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) |
| Vector Store | FAISS (Facebook AI Similarity Search) |
| Charts | Chart.js |
| Database | MySQL (Northwind) |
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
│     Groq LLM (Llama 3.3 70B)    │
│  System Prompt + Schema Context  │
│  + Few-Shot Examples             │
└──────────────┬───────────────────┘
               │ Generated SQL
               ▼
┌──────────────────────────┐
│   MySQL (Northwind DB)   │
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
  (Answer + SQL + Table + Stats)
```

## 🚀 Setup Guide

### Prerequisites
- Python 3.9+
- MySQL Server installed and running
- Groq API key (free at [console.groq.com](https://console.groq.com))

### Step 1: Set up the Northwind Database

```bash
# Download from: https://github.com/dalers/mywind
# Then run in MySQL:
mysql -u root -p < northwind.sql
mysql -u root -p < northwind-data.sql
```

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

Copy `.env.example` to `.env` and fill in your credentials:

```env
MYSQL_USER=root
MYSQL_PASSWORD=your_mysql_password
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
   MYSQL_PASSWORD=northwind123
   ```

2. **Place the Northwind SQL files** in the project root:
   - `northwind.sql` (schema)
   - `northwind-data.sql` (data)

3. **Build and start:**
   ```bash
   docker-compose up --build
   ```

This starts the Flask app + MySQL. The database auto-initializes with the Northwind schema on first run via Docker volume mounts.

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
├── database/
│   ├── connector.py          # MySQL connection pool + safe query execution
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
│   └── index.html            # Chat UI (ChatGPT-style layout)
│
└── static/
    ├── css/styles.css        # Dark/light themes, glassmorphism, animations
    └── js/app.js             # Conversation engine + sidebar + exports
```

## 💬 Example Questions

- *"How many customers are there?"*
- *"Top 5 most expensive products"*
- *"Which employee processed the most orders?"*
- *"Show all orders shipped to New York"*
- *"What is the total revenue by product category?"*
- *"List suppliers from the United States"*
- *"Show monthly sales trends"*

## 🔑 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Serve chat UI |
| POST | `/api/chat` | Send a natural language question, get SQL + results |
| GET | `/api/health` | Health check (DB + RAG + LLM status) |
| GET | `/api/stats` | Database statistics (tables, rows, columns, model) |
| GET | `/api/tables` | List all available tables |

## 📄 License

This project is for educational/academic purposes (capstone project).
