"""Conservative application policy for generated MySQL SELECT queries.

This is an application guard, not a substitute for database permissions or
server-side resource limits. Unsupported syntax and unknown functions fail closed.
"""
import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError


def parse_read_query(sql: str) -> exp.Expression:
    if not isinstance(sql, str) or not sql.strip():
        raise ValueError("A nonempty SQL query is required.")
    # MySQL executes version comments which a generic parser may treat as
    # comments. Reject them, and optimizer hints, rather than silently strip them.
    if "/*!" in sql or "/*+" in sql:
        raise ValueError("Executable comments and optimizer hints are not allowed.")
    try:
        statements = [s for s in sqlglot.parse(sql, read="mysql") if s is not None]
    except SqlglotError as exc:
        raise ValueError("Unsupported or malformed SQL.") from exc
    if len(statements) != 1 or not isinstance(statements[0], (exp.Select, exp.Union)):
        raise ValueError("Exactly one SELECT query (optionally WITH or UNION) is allowed.")
    query = statements[0]
    forbidden = (exp.DML, exp.DDL, exp.Command, exp.Into, exp.Lock,
                 exp.PropertyEQ, exp.Parameter, exp.SessionParameter)
    for node in query.walk():
        if isinstance(node, forbidden):
            raise ValueError("Side effects, locking and session variables are not allowed.")
        if isinstance(node, exp.Anonymous):
            raise ValueError("Unknown or unapproved SQL functions are not allowed.")
    return query


def validate_read_query(sql: str) -> tuple[bool, str]:
    try:
        parse_read_query(sql)
    except ValueError as exc:
        return False, str(exc)
    return True, ""


def prepare_read_query(sql: str, row_limit: int) -> str:
    """Apply an outer result cap; inner LIMITs and string literals cannot bypass it."""
    if isinstance(row_limit, bool) or not isinstance(row_limit, int) or row_limit < 1:
        raise ValueError("The row limit must be a positive integer.")
    query = parse_read_query(sql)
    limit = query.args.get("limit")
    if limit is None:
        query = query.limit(row_limit)
    else:
        value = limit.expression
        if not isinstance(value, exp.Literal) or value.is_string or not value.this.isdigit():
            raise ValueError("LIMIT must be a nonnegative integer literal.")
        query = query.limit(min(int(value.this), row_limit))
    return query.sql(dialect="mysql")
