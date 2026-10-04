"""Ground-truth evaluator regressions: no LLM or database required."""
import importlib.util
from pathlib import Path
import pytest
from types import SimpleNamespace
from unittest.mock import Mock
from agent.agent import SQLAgent
from agent.tools import AgentTools

spec = importlib.util.spec_from_file_location('benchmark_v3', Path(__file__).with_name('benchmark.py'))
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)

def compare(actual, expected, ordered=False):
    function = getattr(benchmark, 'compare_result_rows', None)
    assert callable(function), 'Missing reference-result comparator'
    return function(actual, expected, ordered=ordered)

def test_aliases_do_not_change_result_equivalence():
    assert compare([{'count': 22}], [{'races': '22'}])

def test_unordered_comparison_preserves_duplicates():
    assert compare([{'x': 1}, {'x': 2}], [{'y': 2}, {'y': 1}])
    assert not compare([{'x': 1}, {'x': 1}], [{'y': 1}, {'y': 2}])

def test_ordered_comparison_detects_wrong_ranking():
    assert not compare([{'x': 2}, {'x': 1}], [{'y': 1}, {'y': 2}], ordered=True)

def test_null_empty_and_wrong_shape_are_distinct():
    assert compare([], [])
    assert not compare([{'x': None}], [])
    assert not compare([{'x': None}], [{'x': 0}])
    assert not compare([{'x': 1, 'extra': 2}], [{'x': 1}])

def test_numeric_tolerance_is_small_and_explicit():
    assert compare([{'x': 1.00000001}], [{'x': 1.0}])
    assert not compare([{'x': 1.01}], [{'x': 1.0}])

def test_numeric_strings_do_not_erase_string_identity():
    assert not compare([{'code': '01'}], [{'code': '1'}])

def test_independent_retrieval_labels_include_all_required_tables():
    function = getattr(benchmark, 'score_retrieval', None)
    assert callable(function), 'Missing independent-label retrieval evaluator'
    assert function(['circuits', 'races', 'drivers'], ['races', 'results'], 3) == {
        'reciprocal_rank': 0.5, 'recall_at_k': 0.5, 'precision_at_k': 1/3,
        'all_required_tables_found': False}

def test_legitimate_empty_result_does_not_trigger_rewrite():
    tools = AgentTools(None, None)
    assert tools.validate_results('List circuits on the Moon', 'SELECT name FROM circuits',
                                  {'success': True, 'row_count': 0, 'rows': []})['is_valid']

def test_negative_geographical_measurements_are_valid():
    tools = AgentTools(None, None)
    assert tools.validate_results('Minimum latitude in Brazil', 'SELECT MIN(lat) FROM circuits',
        {'success': True, 'row_count': 1, 'rows': [{'latitude': -23.7}]})['is_valid']

def test_attempt_trace_records_full_executed_query_and_results():
    agent = SQLAgent.__new__(SQLAgent)
    actual = {'success': True, 'rows': [{'n': 22}], 'columns': ['n'],
              'row_count': 1, 'executed_sql': 'SELECT COUNT(*) n FROM races LIMIT 50',
              'row_limit': 50, 'error': None}
    agent.tools = SimpleNamespace(execute_sql=lambda _: actual)
    update = agent._execute_sql({'sql': 'SELECT COUNT(*) n FROM races', 'sql_attempts': 1})
    trace = update['agent_steps'][-1]
    assert trace.get('sql') == actual['executed_sql']
    assert trace.get('execution_result') == actual
    assert trace.get('attempt') == 1

def test_failed_initial_generation_consumes_attempt_budget():
    agent = SQLAgent.__new__(SQLAgent)
    agent.tools = SimpleNamespace(get_system_prompt=lambda _: 'fixture')
    agent.llm = Mock(invoke=Mock(side_effect=RuntimeError('unavailable')))
    update = agent._generate_sql({'question': 'Count races', 'schema_context': '', 'sql_attempts': 0})
    assert update.get('sql_attempts') == 1

def test_unsafe_initial_generation_consumes_attempt_budget():
    agent = SQLAgent.__new__(SQLAgent)
    agent.tools = AgentTools(None, None)
    agent.llm = SimpleNamespace(invoke=lambda _: SimpleNamespace(content='DELETE FROM races'))
    update = agent._generate_sql({'question': 'Count races', 'schema_context': '', 'sql_attempts': 0})
    assert update.get('sql_attempts') == 1

def test_evaluation_summary_keeps_failures_in_accuracy_and_latency():
    summarize = getattr(benchmark, 'summarize_evaluation', None)
    assert callable(summarize), 'Missing execution-evaluation summary'
    records = [dict(final_correct=True,first_attempt_correct=False,retries=1,elapsed_s=8),
               dict(final_correct=False,first_attempt_correct=False,retries=0,elapsed_s=20)]
    summary = summarize(records)
    assert summary['cases'] == 2
    assert summary['final_correct'] == 1
    assert summary['first_attempt_correct'] == 0
    assert summary['final_execution_accuracy'] == 0.5
    assert summary['mean_latency_s'] == 14
    assert summary['retry_recovery_rate'] == 1

def test_empty_evaluation_has_no_fabricated_accuracy_or_retry_rate():
    summarize = getattr(benchmark, 'summarize_evaluation', None)
    assert callable(summarize), 'Missing execution-evaluation summary'
    summary = summarize([])
    assert summary['final_execution_accuracy'] is None
    assert summary['retry_recovery_rate'] is None

def test_counts_are_exact_and_unrounded_averages_are_not_rounded():
    assert not compare([{'n': 1.0000009}], [{'n': 1}])
    assert not compare([{'avg': 122574}], [{'avg': 122574.4857}])

def test_empty_results_still_require_the_requested_projection_width():
    function = getattr(benchmark, 'compare_result_sets', None)
    assert callable(function), 'Missing projection-aware result comparison'
    assert not function({'columns':['name','country'],'rows':[]}, {'columns':['name'],'rows':[]})
    assert function({'columns':['alias'],'rows':[]}, {'columns':['name'],'rows':[]})

def test_numeric_column_metadata_handles_decimal_strings_without_changing_codes():
    function = getattr(benchmark, 'compare_result_sets', None)
    assert callable(function)
    expected = {'columns':['amount'],'numeric_columns':[0],'rows':[{'amount':'1294'}]}
    actual = {'columns':['sum'],'rows':[{'sum':'1294.0'}]}
    assert function(actual, expected)
    expected.pop('numeric_columns')
    assert not function(actual, expected)

def test_provider_failures_are_preserved_even_when_agent_can_fallback(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parent))
    spec = importlib.util.spec_from_file_location('evaluation', Path(__file__).with_name('evaluate.py'))
    evaluation = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(evaluation)
    provider = SimpleNamespace(invoke=Mock(side_effect=ConnectionError('provider down')))
    paced = evaluation.PacedModel(provider)
    with pytest.raises(ConnectionError):
        paced.invoke([SimpleNamespace(content='test')])
    assert len(paced.calls) == 1
    assert paced.calls[0]['error_type'] == 'ConnectionError'
    assert paced.calls[0]['elapsed_s'] >= 0

def test_generation_context_preserves_schema_but_omits_embedding_prose():
    text = ('Table: races\nRow count: 1125\nDescription: calendar history\n'
            'Columns:\n  - raceId: int, not null (PRIMARY KEY)\n  - circuitId: int, nullable (INDEXED)\n'
            'Foreign Keys:\n  - circuitId → circuits.circuitId\n'
            "Sample Data:\n  Row 1: {'raceId': 1}\n")
    tools = AgentTools(None, SimpleNamespace(retrieve=lambda _: text))
    context = tools.schema_lookup('Count races')
    assert 'races' in context and 'raceId' in context and 'circuits.circuitId' in context
    assert 'calendar history' not in context and 'Row 1' not in context

def test_sql_prompt_does_not_supply_an_unretrieved_global_schema():
    tools = AgentTools(None, None)
    prompt = tools.get_system_prompt('Table: circuits\nColumns: circuitId,name,country')
    assert 'driverStandingsId' not in prompt

def test_result_metadata_not_json_key_order_defines_column_order():
    actual={'columns':['person','points'],'rows':[{'points':10,'person':'A'}]}
    expected={'columns':['surname','score'],'rows':[{'surname':'A','score':10}]}
    assert benchmark.compare_result_sets(actual,expected)

def test_fault_probe_corrupts_only_first_execution(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parent))
    spec=importlib.util.spec_from_file_location('evaluation',Path(__file__).with_name('evaluate.py'))
    evaluation=importlib.util.module_from_spec(spec); spec.loader.exec_module(evaluation)
    probe_type=getattr(evaluation,'FaultProbeTools',None)
    assert callable(probe_type), 'Missing controlled execution-error probe'
    queries=[]
    def execute(sql):
        queries.append(sql)
        return {'success':'__f1_probe_missing_column__' not in sql,'rows':[]}
    probe=probe_type(SimpleNamespace(execute_query=execute),None)
    assert not probe.execute_sql('SELECT COUNT(*) FROM races')['success']
    assert probe.execute_sql('SELECT COUNT(*) FROM races')['success']
    assert '__f1_probe_missing_column__' in queries[0]
    assert '__f1_probe_missing_column__' not in queries[1]

def test_local_setup_overrides_config_imported_before_environment(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parent))
    import database.connector as connector
    from config import Config
    monkeypatch.setattr(Config,'MYSQL_HOST','production.example')
    monkeypatch.setattr(Config,'MYSQL_PORT',4000)
    monkeypatch.setattr(Config,'MYSQL_USER','production_writer')
    monkeypatch.setattr(connector,'DatabaseConnector',lambda: (Config.MYSQL_HOST,Config.MYSQL_PORT,Config.MYSQL_USER))
    spec=importlib.util.spec_from_file_location('evaluation',Path(__file__).with_name('evaluate.py'))
    evaluation=importlib.util.module_from_spec(spec); spec.loader.exec_module(evaluation)
    assert evaluation.setup_local()==('127.0.0.1',33070,'f1_eval_reader')

def test_benchmark_client_actually_disables_sdk_retries_and_bounds_timeout(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parent))
    spec=importlib.util.spec_from_file_location('evaluation',Path(__file__).with_name('evaluate.py'))
    evaluation=importlib.util.module_from_spec(spec); spec.loader.exec_module(evaluation)
    build=getattr(evaluation,'build_benchmark_model',None)
    assert callable(build), 'Missing correctly constructed benchmark client'
    model=build('nonsecret-offline-fixture','openai/gpt-oss-120b')
    assert model.client._client.max_retries==0
    assert model.client._client.timeout==60

def test_database_failure_trace_keeps_the_exact_capped_query():
    from database.connector import DatabaseConnector
    from mysql.connector import Error
    cursor=SimpleNamespace(execute=Mock(side_effect=Error('Unknown column',errno=1054)),close=lambda:None)
    connection=SimpleNamespace(cursor=lambda **_:cursor,close=lambda:None)
    db=DatabaseConnector.__new__(DatabaseConnector)
    db.get_connection=lambda:connection
    response=db.execute_query('SELECT missing FROM races')
    assert response.get('executed_sql')=='SELECT missing FROM races LIMIT 50'
    assert not response['success']
