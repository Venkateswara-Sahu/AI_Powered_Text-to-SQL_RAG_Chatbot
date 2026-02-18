"""Flask application — NorthwindAI Text-to-SQL Chatbot."""

import time
from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
from config import Config
from database.connector import DatabaseConnector
from rag.embeddings import SchemaRAG
from llm.sql_generator import SQLGenerator

# ── Initialize Flask ──────────────────────────────────────────
app = Flask(__name__)
app.secret_key = Config.FLASK_SECRET_KEY
CORS(app)

# ── Initialize Components ────────────────────────────────────
print("\n" + "=" * 50)
print("  NorthwindAI — Starting up...")
print("=" * 50 + "\n")

# Database
db = DatabaseConnector()  
# RAG
rag = SchemaRAG()
# LLM
llm = SQLGenerator()

# Index schema into RAG at startup
print("[INIT] Building schema index...")
schema_info = db.get_schema_info()
rag.index_schema(schema_info)
print("[INIT] Ready!\n")


# ── Routes ────────────────────────────────────────────────────

@app.route("/")
def index():
    """Serve the chat UI."""
    return render_template("index.html")


@app.route("/api/health", methods=["GET"])
def health_check():
    """Check system health: database + LLM."""
    db_ok = db.test_connection()
    return jsonify({
        "status": "healthy" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
        "model": Config.GROQ_MODEL,
        "rag_indexed": rag._is_indexed,
    })


@app.route("/api/tables", methods=["GET"])
def get_tables():
    """Return list of available tables."""
    tables = rag.get_all_table_names()
    return jsonify({"tables": tables, "count": len(tables)})


@app.route("/api/stats", methods=["GET"])
def get_stats():
    """Return database statistics for the welcome screen."""
    tables = rag.get_all_table_names()
    total_rows = sum(t.get("row_count", 0) for t in schema_info)
    total_columns = sum(len(t.get("columns", [])) for t in schema_info)
    return jsonify({
        "table_count": len(tables),
        "total_rows": total_rows,
        "total_columns": total_columns,
        "model": Config.GROQ_MODEL,
        "database": Config.MYSQL_DATABASE,
    })


@app.route("/api/chat", methods=["POST"])
def chat():
    """Main chat endpoint — process user question through RAG → SQL → Answer pipeline."""
    data = request.get_json()
    if not data or "message" not in data:
        return jsonify({"error": "No message provided"}), 400

    question = data["message"].strip()
    if not question:
        return jsonify({"error": "Empty message"}), 400

    # Initialize session chat history
    if "chat_history" not in session:
        session["chat_history"] = []

    start_time = time.time()

    try:
        # Step 1: Retrieve relevant schema context via RAG
        schema_context = rag.retrieve(question)

        # Step 2: Generate SQL using LLM
        sql_result = llm.generate_sql(question, schema_context)
        sql = sql_result.get("sql", "")

        if not sql or not sql_result.get("is_valid", False):
            elapsed = round(time.time() - start_time, 2)
            return jsonify({
                "answer": sql_result.get("error") or "I couldn't generate a SQL query for that question. Could you rephrase it?",
                "sql": sql if sql else None,
                "results": None,
                "execution_time": elapsed,
                "error": sql_result.get("error")
            })

        # Step 3: Execute the SQL query
        result = db.execute_query(sql)

        if not result["success"]:
            # Step 3b: Retry with error feedback
            retry_result = llm.retry_sql(question, schema_context, sql, result["error"])
            retry_sql = retry_result.get("sql", "")
            if retry_sql and retry_result.get("is_valid", False):
                result = db.execute_query(retry_sql)
                if result["success"]:
                    sql = retry_sql

        # Step 4: Generate natural language answer
        if result["success"]:
            answer = llm.generate_answer(question, sql, result)
        else:
            answer = f"I generated the SQL but it failed to execute: {result['error']}"

        # Step 5: Generate follow-up suggestions
        follow_ups = []
        if result["success"] and answer:
            try:
                follow_ups = llm.generate_follow_ups(question, answer)
            except Exception:
                pass  # Non-critical, skip if it fails

        elapsed = round(time.time() - start_time, 2)

        # Update chat history
        session["chat_history"] = session.get("chat_history", [])
        session["chat_history"].append({"role": "user", "content": question})
        session["chat_history"].append({"role": "assistant", "content": answer})
        # Keep history manageable
        if len(session["chat_history"]) > 20:
            session["chat_history"] = session["chat_history"][-20:]
        session.modified = True

        return jsonify({
            "answer": answer,
            "sql": sql,
            "results": {
                "columns": result.get("columns", []),
                "rows": result.get("rows", []),
                "row_count": result.get("row_count", 0),
            } if result["success"] else None,
            "execution_time": elapsed,
            "follow_ups": follow_ups,
            "error": result.get("error") if not result["success"] else None,
        })

    except Exception as e:
        elapsed = round(time.time() - start_time, 2)
        print(f"[ERROR] Chat pipeline failed: {e}")
        return jsonify({
            "answer": None,
            "sql": None,
            "results": None,
            "execution_time": elapsed,
            "error": f"An unexpected error occurred: {str(e)}"
        }), 500


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=Config.FLASK_DEBUG
    )
