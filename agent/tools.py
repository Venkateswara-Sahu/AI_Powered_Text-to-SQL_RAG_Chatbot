"""Agent tools — callable functions the LangGraph agent can invoke."""

import re
from database.connector import DatabaseConnector
from rag.embeddings import SchemaRAG
from llm.prompt_templates import SYSTEM_PROMPT, FEW_SHOT_EXAMPLES


class AgentTools:
    """Provides tools for the LangGraph agent to use."""

    def __init__(self, db: DatabaseConnector, rag: SchemaRAG):
        self.db = db
        self.rag = rag

    def schema_lookup(self, question: str) -> str:
        """Retrieve relevant schema context for a question using FAISS RAG."""
        try:
            context = self.rag.retrieve(question)
            return context if context else "No relevant schema found."
        except Exception as e:
            return f"Schema lookup failed: {str(e)}"

    def execute_sql(self, sql: str) -> dict:
        """Execute a read-only SQL query safely."""
        return self.db.execute_query(sql)

    def validate_results(self, question: str, sql: str, results: dict) -> dict:
        """
        Validate query results for sanity.
        Returns dict with is_valid, issues list.
        """
        issues = []

        if not results.get("success"):
            return {"is_valid": False, "issues": [results.get("error", "Unknown error")]}

        row_count = results.get("row_count", 0)
        rows = results.get("rows", [])

        # Check for empty results on questions that expect data
        question_lower = question.lower()
        if row_count == 0:
            expecting_data = any(w in question_lower for w in [
                "how many", "count", "total", "list", "show", "top", "all"
            ])
            if expecting_data:
                issues.append(f"Query returned 0 rows but the question expects data. The SQL might be too restrictive.")

        # Check for suspiciously large single values
        if rows and len(rows) == 1:
            for key, val in rows[0].items():
                if isinstance(val, (int, float)) and val < 0:
                    issues.append(f"Negative value found in '{key}': {val}. This might indicate a calculation error.")

        return {
            "is_valid": len(issues) == 0,
            "issues": issues,
            "row_count": row_count,
        }

    def get_system_prompt(self, schema_context: str) -> str:
        """Build the full system prompt with schema context and few-shot examples."""
        return SYSTEM_PROMPT.format(schema_context=schema_context) + "\n" + FEW_SHOT_EXAMPLES

    @staticmethod
    def extract_sql(response_text: str) -> str:
        """Extract clean SQL from LLM response."""
        text = response_text.strip()

        # Remove markdown code blocks
        match = re.search(r"```(?:sql)?\s*\n?(.*?)\n?```", text, re.DOTALL | re.IGNORECASE)
        if match:
            text = match.group(1).strip()

        text = text.strip("`").strip()

        # Extract SQL statements
        lines = text.split("\n")
        sql_lines = []
        in_sql = False
        for line in lines:
            stripped = line.strip().upper()
            if stripped.startswith(("SELECT", "WITH", "SHOW")):
                in_sql = True
            if in_sql:
                sql_lines.append(line)

        if sql_lines:
            text = "\n".join(sql_lines)

        text = text.rstrip(";").strip() + ";"
        return text

    @staticmethod
    def validate_sql_safety(sql: str) -> tuple:
        """Check SQL is read-only. Returns (is_safe, error)."""
        blocked = [
            "DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE",
            "CREATE", "REPLACE", "RENAME", "GRANT", "REVOKE"
        ]
        upper = sql.upper()
        for kw in blocked:
            if re.search(rf"\b{kw}\b", upper):
                return False, f"Blocked: SQL contains '{kw}'"

        if not (upper.lstrip().startswith("SELECT") or
                upper.lstrip().startswith("WITH") or
                upper.lstrip().startswith("SHOW")):
            return False, "Only SELECT/WITH/SHOW queries are allowed."

        return True, ""
