"""Agent tools — callable functions the LangGraph agent can invoke."""
from __future__ import annotations

import re
from database.connector import DatabaseConnector
from typing import TYPE_CHECKING
from sqlglot import parse_one, exp
from sqlglot.errors import SqlglotError
from sqlglot.optimizer.scope import traverse_scope
from database.sql_policy import validate_read_query, parse_read_query
if TYPE_CHECKING:
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
            if not context:
                return "No relevant schema found."
            # Rich prose/sample rows support retrieval; SQL generation needs
            # exact column names/types/keys rather than repeated index prose.
            compact=[]
            for document in context.split("\n---\n"):
                table=[]
                section=None
                for line in document.splitlines():
                    stripped=line.strip()
                    if stripped.startswith('Table:'):
                        table.append(stripped)
                    elif stripped in ('Columns:','Foreign Keys:'):
                        section=stripped
                    elif stripped.startswith('Sample Data:'):
                        section=None
                    elif stripped.startswith('- ') and section:
                        table.append(stripped)
                compact.append('\n'.join(table))
            return '\n---\n'.join(compact)
        except Exception as e:
            return f"Schema lookup failed: {str(e)}"

    def execute_sql(self, sql: str) -> dict:
        """Execute SELECT SQL with human-name equality normalization.

        Only literal equalities on physical drivers.forename/surname change.
        Stable identifiers, patterns, other tables and CTE shadows retain their
        semantics. Validate the original first so parsing cannot erase unsafe
        executable comments. The connector records the actual normalized SQL.
        """
        try:
            query = parse_read_query(sql)
        except ValueError:
            return self.db.execute_query(sql)
        # Resolve TiDB's case-insensitive aliases/CTEs on a separate tree.
        # Keep emitted identifier spelling, including quoted names, unchanged.
        resolution = query.copy()
        original_columns = {id(copy): original for copy, original in
            zip(resolution.find_all(exp.Column), query.find_all(exp.Column))}
        for identifier in resolution.find_all(exp.Identifier):
            identifier.set('this', identifier.this.lower())
        for scope in traverse_scope(resolution):
            for resolved_column in scope.columns:
                if resolved_column.name not in ('forename', 'surname'):
                    continue
                source = scope.sources.get(resolved_column.table)
                if not resolved_column.table and len(scope.sources) == 1:
                    source = next(iter(scope.sources.values()))
                if not isinstance(source, exp.Table) or source.name.lower() != 'drivers':
                    continue
                column = original_columns[id(resolved_column)]
                equality = column.parent
                if not isinstance(equality, exp.EQ):
                    continue
                other = equality.expression if equality.this is column else equality.this
                if not isinstance(other, exp.Literal) or not other.is_string:
                    continue
                column.replace(exp.Collate(this=column.copy(),
                    expression=exp.Var(this='utf8mb4_unicode_ci')))
        return self.db.execute_query(query.sql(dialect='mysql'))

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

        # Empty sets and negative values can be correct (absent entities,
        # geographical coordinates or signed differences). Without independent
        # ground truth they are not grounds for changing a successfully executed
        # query. Retry execution errors; evaluate semantic correctness separately.

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
    def extract_tables_from_sql(sql: str) -> list[str]:
        """Extract table names referenced in a SQL query (FROM and JOIN clauses)."""
        if not sql:
            return []
        try:
            query = parse_one(sql, read="mysql")
        except SqlglotError:
            return []
        # TiDB resolves table/CTE identifiers case-insensitively. Normalize
        # before scope resolution, not just when returning table names.
        for identifier in query.find_all(exp.Identifier):
            identifier.set("this", identifier.this.lower())
        physical_tables = {id(source) for scope in traverse_scope(query)
                           for source in scope.sources.values()
                           if isinstance(source, exp.Table)}
        matches = [table.name for table in query.find_all(exp.Table)
                   if id(table) in physical_tables]
        # Deduplicate while preserving order
        seen = set()
        tables = []
        for t in matches:
            t_lower = t.lower()
            if t_lower not in seen:
                seen.add(t_lower)
                tables.append(t_lower)
        return tables

    @staticmethod
    def compute_faithfulness(answer: str, execution_result: dict) -> dict:
        """
        Heuristic substring coverage of selected result values in answer text.
        This does not establish factual correctness or semantic faithfulness.

        Returns:
            dict with score (0-1), matched, total, details
        """
        if not answer or not execution_result.get("success"):
            return {"score": None, "matched": 0, "total": 0, "details": []}

        rows = execution_result.get("rows", [])
        if not rows:
            return {"score": None, "matched": 0, "total": 0, "details": []}

        answer_lower = answer.lower()

        # Extract key values from the first few rows of results
        values_to_check = []
        for row in rows[:5]:  # Check top 5 rows
            for key, val in row.items():
                if val is None:
                    continue
                val_str = str(val).strip()
                if not val_str or len(val_str) < 2:
                    continue
                # Skip ID-like columns
                if key.lower().endswith("id") or key.lower() == "url":
                    continue
                values_to_check.append({"column": key, "value": val_str})

        if not values_to_check:
            return {"score": None, "matched": 0, "total": 0, "details": []}

        # Check each value in the answer
        matched = 0
        details = []
        for item in values_to_check:
            found = item["value"].lower() in answer_lower
            if found:
                matched += 1
            details.append({
                "column": item["column"],
                "value": item["value"],
                "found": found,
            })

        total = len(values_to_check)
        score = round(matched / total, 4) if total > 0 else None

        return {
            "score": score,
            "matched": matched,
            "total": total,
            "details": details,
        }

    @staticmethod
    def validate_sql_safety(sql: str) -> tuple:
        """Apply the same parsed-query policy used at database execution."""
        return validate_read_query(sql)
