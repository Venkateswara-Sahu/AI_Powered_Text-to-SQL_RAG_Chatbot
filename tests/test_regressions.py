import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from agent.agent import SQLAgent
from agent.tools import AgentTools
from config import Config
from database.connector import DatabaseConnector

spec = importlib.util.spec_from_file_location("benchmark", Path(__file__).with_name("benchmark.py"))
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


def run_recorded_case(monkeypatch, tmp_path, payload=None, exception=None):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "tests").mkdir()
    monkeypatch.setattr(benchmark, "TEST_QUERIES", [{
        "question": "Show drivers", "category": "Fixture", "expect_sql": True,
        "validation": ["alpha"],
    }])
    response = SimpleNamespace(status_code=200, json=lambda: payload)
    monkeypatch.setattr(benchmark.requests, "post", Mock(return_value=response, side_effect=exception))
    clock = iter([10.0, 14.0])
    monkeypatch.setattr(benchmark.time, "time", lambda: next(clock))
    monkeypatch.setattr(benchmark.time, "perf_counter", lambda: next(clock))
    result = benchmark.run_benchmark()
    return result


def response_payload(steps):
    return {"answer": "alpha", "sql": "SELECT name FROM drivers",
            "results": {"columns": ["name"], "rows": [{"name": "alpha"}], "row_count": 1},
            "agent_steps": steps, "error": None, "execution_time": 4,
            "follow_ups": [], "rag_metrics": {}, "conversation_id": "fixture"}


def test_benchmark_counts_api_retry_trace(monkeypatch, tmp_path):
    result = run_recorded_case(monkeypatch, tmp_path, response_payload([
        {"node": "execute_sql", "detail": "failed"},
        {"node": "retry_sql", "detail": "retry"},
        {"node": "execute_sql", "detail": "success"},
    ]))
    assert result["retries_needed"] == 1
    assert result["retry_success_rate"] == 100.0


def test_unexercised_retries_have_no_success_estimate(monkeypatch, tmp_path):
    result = run_recorded_case(monkeypatch, tmp_path, response_payload([]))
    assert result["retry_success_rate"] is None


def test_timeout_contributes_to_latency(monkeypatch, tmp_path):
    result = run_recorded_case(monkeypatch, tmp_path, exception=requests.exceptions.Timeout())
    assert result["avg_response_time"] == 4.0


def test_null_results_are_classified_without_a_parser_exception(monkeypatch, tmp_path):
    payload = response_payload([])
    payload.update(results=None, error="Execution failed")
    result = run_recorded_case(monkeypatch, tmp_path, payload)
    assert result["results"][0].get("error") == "Execution failed"


@pytest.mark.parametrize("sql", [
    "SELECT 1; SELECT 2", "SELECT 1 INTO OUTFILE '/tmp/probe'",
    "SELECT SLEEP(10)", "SELECT LOAD_FILE('/tmp/probe')",
    "SELECT * FROM drivers FOR UPDATE", "SELECT @x := 1",
    "SELECT 1 /*! INTO OUTFILE '/tmp/probe' */",
])
def test_both_sql_entry_points_reject_side_effects(sql):
    db = DatabaseConnector.__new__(DatabaseConnector)
    assert db._is_safe_query(sql) is False
    assert AgentTools.validate_sql_safety(sql)[0] is False


def test_literal_write_keywords_are_ordinary_data():
    sql = "SELECT 'please UPDATE this text' AS note"
    db = DatabaseConnector.__new__(DatabaseConnector)
    assert db._is_safe_query(sql) is True
    assert AgentTools.validate_sql_safety(sql)[0] is True


def test_reciprocal_rank_uses_best_retrieved_relevant_table():
    agent = SQLAgent.__new__(SQLAgent)
    agent.tools = AgentTools(None, None)
    metrics = agent._compute_rag_metrics({
        "sql": "SELECT * FROM races JOIN drivers ON races.winner = drivers.driverId",
        "retrieved_tables": [{"table": "drivers"}, {"table": "races"}],
        "execution_result": {"success": True, "rows": [{"name": "alpha"}]},
    }, "alpha")
    assert metrics["mrr"] == 1.0


def test_empty_value_check_has_no_faithfulness_estimate():
    result = AgentTools.compute_faithfulness("No rows", {"success": True, "rows": []})
    assert result["score"] is None


def test_pool_and_fallback_verify_tls(monkeypatch):
    monkeypatch.setattr(Config, "MYSQL_SSL", True)
    captured = []
    class StalePool:
        def get_connection(self):
            from mysql.connector import Error
            raise Error("stale pool")
    def make_pool(**kwargs):
        captured.append(kwargs)
        return StalePool()
    def connect(**kwargs):
        captured.append(kwargs)
        return object()
    monkeypatch.setattr("database.connector.pooling.MySQLConnectionPool", make_pool)
    monkeypatch.setattr("database.connector.mysql.connector.connect", connect)
    db = DatabaseConnector()
    db.get_connection()
    assert len(captured) == 2
    for settings in captured:
        assert settings["ssl_verify_cert"] is True
        assert settings["ssl_verify_identity"] is True


def test_large_explicit_limit_is_capped_at_execution():
    from sqlglot import parse_one, exp
    executed = []
    class Cursor:
        description = [("name",)]
        def execute(self, sql):
            executed.append(sql)
        def fetchall(self):
            return [{"name": "alpha"}]
        def close(self):
            pass
    connection = SimpleNamespace(cursor=lambda **kwargs: Cursor(), close=lambda: None)
    db = DatabaseConnector.__new__(DatabaseConnector)
    db.get_connection = lambda: connection
    result = db.execute_query("SELECT name FROM drivers LIMIT 100000", limit=50)
    assert result["success"] is True
    parsed = parse_one(executed[0], read="mysql")
    assert int(parsed.args["limit"].expression.this) == 50


def test_limit_inside_a_literal_does_not_disable_the_row_cap():
    executed = []
    class Cursor:
        description = [("note",)]
        def execute(self, sql):
            executed.append(sql)
        def fetchall(self):
            return [{"note": "LIMIT"}]
        def close(self):
            pass
    db = DatabaseConnector.__new__(DatabaseConnector)
    db.get_connection = lambda: SimpleNamespace(cursor=lambda **kwargs: Cursor(), close=lambda: None)
    db.execute_query("SELECT 'LIMIT' AS note", limit=2)
    from sqlglot import parse_one
    assert parse_one(executed[0], read="mysql").args.get("limit") is not None


def test_table_proxy_excludes_cte_aliases_and_reads_qualified_tables():
    sql = "WITH winners AS (SELECT * FROM f1db.results) SELECT * FROM winners JOIN drivers d ON winners.driverId=d.driverId"
    assert AgentTools.extract_tables_from_sql(sql) == ["drivers", "results"]


def test_retry_pass_is_not_counted_as_a_pass_without_retry(monkeypatch, tmp_path):
    result = run_recorded_case(monkeypatch, tmp_path, response_payload([{ "node": "retry_sql" }]))
    assert result.get("sql_checks_passed_without_retry") == 0


def test_result_value_check_is_explicitly_a_proxy():
    agent = SQLAgent.__new__(SQLAgent)
    agent.tools = AgentTools(None, None)
    metrics = agent._compute_rag_metrics({"sql": "SELECT * FROM drivers",
        "retrieved_tables": [{"table": "drivers"}],
        "execution_result": {"success": True, "rows": []}}, "No rows")
    assert metrics.get("relevance_source") == "generated_sql_table_proxy"
    assert metrics.get("answer_check_type") == "result_value_substring_coverage"


def test_sql_only_query_suite_can_be_empty(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    result = benchmark.run_benchmark(queries=[])
    assert result["sql_check_pass_rate"] is None
    assert result["avg_response_time"] is None


def test_benchmark_preserves_missing_trace_as_unknown(monkeypatch, tmp_path):
    payload = response_payload([])
    del payload["agent_steps"]
    result = run_recorded_case(monkeypatch, tmp_path, payload)
    assert result["results"][0]["retries"] is None
    assert result["sql_checks_passed_without_retry"] == 0


def test_benchmark_does_not_overwrite_existing_artifacts(tmp_path):
    path = tmp_path / "existing.json"
    path.write_text("historical data")
    with pytest.raises(FileExistsError):
        benchmark.run_benchmark(queries=[], output_path=path)
    assert path.read_text() == "historical data"


@pytest.mark.parametrize("sql", [
    "WITH a AS (SELECT 1 AS x) SELECT x FROM a",
    "SELECT COUNT(*) FROM results",
    "SELECT driverId FROM results UNION SELECT driverId FROM drivers",
])
def test_valid_domain_selects_are_accepted(sql):
    assert AgentTools.validate_sql_safety(sql)[0] is True


def test_policy_rejects_unsupported_show_statements():
    assert AgentTools.validate_sql_safety("SHOW TABLES")[0] is False


def test_scoped_cte_name_does_not_hide_a_real_table():
    sql = "SELECT * FROM drivers WHERE EXISTS (WITH drivers AS (SELECT * FROM races) SELECT * FROM drivers)"
    assert set(AgentTools.extract_tables_from_sql(sql)) == {"drivers", "races"}


def test_tidb_case_insensitive_cte_is_not_a_physical_table():
    sql = "WITH Winners AS (SELECT * FROM races) SELECT * FROM winners"
    assert AgentTools.extract_tables_from_sql(sql) == ["races"]
