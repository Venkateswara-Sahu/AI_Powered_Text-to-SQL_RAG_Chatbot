"""Regressions for separately documented repairs after the frozen evaluation."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlglot import parse_one, exp
from agent.agent import SQLAgent
from agent.tools import AgentTools
from database.sql_policy import validate_read_query


@pytest.mark.parametrize('size', [21, 50])
def test_large_answer_lists_preserve_every_returned_row_without_model_truncation(size):
    agent = SQLAgent.__new__(SQLAgent)
    agent.llm = Mock(invoke=Mock(return_value=SimpleNamespace(content='First twenty rows only')))
    agent._compute_rag_metrics = lambda *_: {}
    rows = [{'event': f'UniqueEvent{i:02}', 'round': i} for i in range(1, size + 1)]
    answer = agent._generate_answer({'question': 'List all events in order',
        'execution_result': {'success': True, 'rows': rows, 'columns': ['event', 'round'], 'row_count': size}})['answer']
    assert all(answer.count(row['event']) == 1 for row in rows)
    assert [answer.index(row['event']) for row in rows] == sorted(answer.index(row['event']) for row in rows)
    agent.llm.invoke.assert_not_called()


@pytest.mark.parametrize('sql', [
    "SELECT surname FROM drivers d WHERE d.surname='Perez'",
    "SELECT surname FROM drivers WHERE surname='Raikkonen'",
    "SELECT d.surname FROM drivers d JOIN results r USING(driverId) WHERE 'Hulkenberg'=d.surname",
    "SELECT d.surname FROM drivers d WHERE d.forename='Jose'",
    "SELECT D.surname FROM drivers AS D WHERE d.surname='Perez'",
])
def test_driver_display_name_equalities_use_accent_insensitive_comparison(sql):
    db = SimpleNamespace(execute_query=Mock(return_value={'success': True}))
    AgentTools(db, None).execute_sql(sql)
    actual = db.execute_query.call_args.args[0]
    assert 'utf8mb4_unicode_ci' in actual.lower()
    assert validate_read_query(actual)[0]


@pytest.mark.parametrize('sql', [
    "SELECT surname FROM other_table WHERE surname='Perez'",
    "WITH drivers AS (SELECT surname FROM other_table) SELECT surname FROM drivers WHERE surname='Perez'",
    "WITH DRIVERS AS (SELECT surname FROM other_table) SELECT d.surname FROM drivers d WHERE d.surname='Perez'",
    "WITH drivers AS (SELECT surname FROM other_table) SELECT d.surname FROM DRIVERS d WHERE d.surname='Perez'",
    "SELECT driverRef FROM drivers WHERE driverRef='perez'",
    "SELECT d.surname FROM drivers d WHERE d.surname LIKE 'Per%'",
])
def test_name_matching_does_not_rewrite_unrelated_entities_identifiers_or_patterns(sql):
    db = SimpleNamespace(execute_query=Mock(return_value={'success': True}))
    AgentTools(db, None).execute_sql(sql)
    actual = db.execute_query.call_args.args[0]
    assert 'utf8mb4_unicode_ci' not in actual.lower()


def test_name_repair_preserves_rejected_executable_comments():
    db = SimpleNamespace(execute_query=Mock(return_value={'success': False}))
    sql = "SELECT surname FROM drivers WHERE surname='Perez' /*! INTO OUTFILE '/tmp/data' */"
    AgentTools(db, None).execute_sql(sql)
    assert db.execute_query.call_args.args[0] == sql
    assert not validate_read_query(sql)[0]
