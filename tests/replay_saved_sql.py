"""Replay saved generated queries after repairs, without calling a model.

This is a deterministic repair check, never a fresh generative accuracy score.
Requires the isolated snapshot described in docs/ground-truth-evaluation.md.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluate import setup_local, verify_snapshot
from benchmark import compare_result_sets
from agent.tools import AgentTools
from agent.agent import SQLAgent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact', type=Path, default=ROOT/'docs/evaluation/evaluation.json')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output exists; choose a new artifact path.')
    data = json.loads(args.artifact.read_text(encoding='utf-8'))
    db = setup_local()
    verify_snapshot(db, data['snapshot'])
    tools = AgentTools(db, None)
    agent = SQLAgent.__new__(SQLAgent)
    agent._compute_rag_metrics = lambda *_: {}
    records = []
    for case in data['cases']:
        actual = tools.execute_sql(case['response']['sql'])
        record = {'id': case['id'], 'execution': actual,
            'reference_match': actual['success'] and compare_result_sets(actual,
                case['expected_result'], ordered=case['ordered'])}
        if actual['success'] and len(actual['rows']) > 20:
            record['direct_answer'] = agent._generate_answer({'question': case['question'],
                'sql': actual['executed_sql'], 'execution_result': actual})['answer']
            assert len(record['direct_answer'].splitlines()) == len(actual['rows'])
        records.append(record)
    verify_snapshot(db, data['snapshot'])
    result = {'method': 'Saved-SQL repair replay; no new model calls',
        'source_artifact_sha256': hashlib.sha256(args.artifact.read_bytes()).hexdigest(),
        'original_frozen_implementation': data['implementation_commit'],
        'replayed_queries': len(records), 'reference_matches': sum(c['reference_match'] for c in records),
        'records': records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as output:
        json.dump(result, output, indent=2, ensure_ascii=False, default=str)
    print(f"Saved SQL: {result['reference_matches']}/{len(records)} matches; no new model calls.")


if __name__ == '__main__':
    main()
