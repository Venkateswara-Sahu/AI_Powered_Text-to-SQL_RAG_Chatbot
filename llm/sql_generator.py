import re
from groq import Groq
from config import Config
from llm.prompt_templates import (
    SYSTEM_PROMPT,
    FEW_SHOT_EXAMPLES,
    USER_PROMPT_TEMPLATE,
    RETRY_PROMPT_TEMPLATE,
    ANSWER_SYSTEM_PROMPT,
    ANSWER_USER_TEMPLATE,
)


class SQLGenerator:
    """
    Text-to-SQL engine powered by Groq API.
    Generates SQL from natural language, validates it, and
    synthesizes natural language answers from query results.
    """

    def __init__(self):
        """Initialize the Groq client."""
        if not Config.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY is not set. Get one at https://console.groq.com")
        self.client = Groq(api_key=Config.GROQ_API_KEY)
        self.model = Config.GROQ_MODEL
        print(f"[LLM] Groq client initialized (model: {self.model})")

    def _extract_sql(self, response_text: str) -> str:
        """Extract clean SQL from LLM response, handling markdown code blocks."""
        text = response_text.strip()

        # Remove markdown code blocks if present
        code_block_match = re.search(r"```(?:sql)?\s*\n?(.*?)\n?```", text, re.DOTALL | re.IGNORECASE)
        if code_block_match:
            text = code_block_match.group(1).strip()

        # Remove any leading/trailing backticks
        text = text.strip("`").strip()

        # Remove any non-SQL preamble (take last SQL statement if multiple)
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

        # Clean up
        text = text.rstrip(";").strip() + ";"
        return text

    def _validate_sql(self, sql: str) -> tuple[bool, str]:
        """
        Validate that the SQL is safe to execute.
        Returns (is_valid, error_message).
        """
        blocked = [
            "DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE",
            "CREATE", "REPLACE", "RENAME", "GRANT", "REVOKE"
        ]
        upper_sql = sql.upper()

        for keyword in blocked:
            if re.search(rf"\b{keyword}\b", upper_sql):
                return False, f"Blocked: SQL contains '{keyword}' which is not allowed."

        if not (upper_sql.lstrip().startswith("SELECT") or
                upper_sql.lstrip().startswith("WITH") or
                upper_sql.lstrip().startswith("SHOW")):
            return False, "Only SELECT/WITH/SHOW queries are allowed."

        return True, ""

    def generate_sql(self, question: str, schema_context: str) -> dict:
        """
        Generate SQL from a natural language question.

        Args:
            question: User's natural language question
            schema_context: Retrieved schema context from RAG

        Returns:
            dict with keys: sql, is_valid, error
        """
        system_message = SYSTEM_PROMPT.format(schema_context=schema_context)
        system_message += "\n" + FEW_SHOT_EXAMPLES
        user_message = USER_PROMPT_TEMPLATE.format(question=question)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.1,  # Low temperature for deterministic SQL
                max_tokens=1024,
            )

            raw_response = response.choices[0].message.content
            sql = self._extract_sql(raw_response)
            is_valid, error = self._validate_sql(sql)

            return {
                "sql": sql,
                "is_valid": is_valid,
                "error": error if not is_valid else None,
                "raw_response": raw_response,
            }

        except Exception as e:
            return {
                "sql": "",
                "is_valid": False,
                "error": f"LLM error: {str(e)}",
                "raw_response": "",
            }

    def retry_sql(self, question: str, schema_context: str,
                  failed_sql: str, error: str) -> dict:
        """
        Retry SQL generation with error feedback.

        Args:
            question: Original question
            schema_context: Schema context
            failed_sql: The SQL that failed
            error: The error message

        Returns:
            dict with keys: sql, is_valid, error
        """
        system_message = SYSTEM_PROMPT.format(schema_context=schema_context)
        retry_message = RETRY_PROMPT_TEMPLATE.format(
            error=error,
            failed_sql=failed_sql,
            question=question,
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": retry_message},
                ],
                temperature=0.1,
                max_tokens=1024,
            )

            raw_response = response.choices[0].message.content
            sql = self._extract_sql(raw_response)
            is_valid, val_error = self._validate_sql(sql)

            return {
                "sql": sql,
                "is_valid": is_valid,
                "error": val_error if not is_valid else None,
                "raw_response": raw_response,
            }

        except Exception as e:
            return {
                "sql": "",
                "is_valid": False,
                "error": f"LLM retry error: {str(e)}",
                "raw_response": "",
            }

    def generate_answer(self, question: str, sql: str,
                        results: dict) -> str:
        """
        Generate a natural language answer from query results.

        Args:
            question: Original user question
            sql: The SQL query that was executed
            results: Query results dict from DatabaseConnector

        Returns:
            Natural language answer string
        """
        # Format results for the prompt
        if results["success"] and results["rows"]:
            results_text = ""
            for i, row in enumerate(results["rows"][:20]):  # Limit to 20 rows
                results_text += f"  {row}\n"
            if results["row_count"] > 20:
                results_text += f"  ... and {results['row_count'] - 20} more rows\n"
        elif results["success"] and not results["rows"]:
            results_text = "  (No results found)"
        else:
            results_text = f"  Error: {results['error']}"

        user_message = ANSWER_USER_TEMPLATE.format(
            question=question,
            sql=sql,
            row_count=results["row_count"],
            results=results_text,
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.5,
                max_tokens=512,
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            return f"I found the results but couldn't generate a summary: {str(e)}"
