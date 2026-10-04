"""
F1InsightAI — Performance Benchmark Script
Runs a set of test queries through the API and measures accuracy metrics.
Usage: python tests/benchmark.py
Requires: App running on localhost:5000
"""

import requests
import json
import time
import sys

API_URL = "http://localhost:5000/api/chat"


def compare_result_rows(actual, expected, ordered=False, rel_tol=0, abs_tol=1e-6):
    """Compare projections by column position, preserving multiplicity and NULL.

    Aliases are immaterial; projection width/order is part of the question contract.
    Numeric serialization differences are tolerated, but two strings remain strings.
    """
    from decimal import Decimal, InvalidOperation
    from numbers import Number
    from math import isclose
    if len(actual) != len(expected):
        return False

    def equal_value(a, b):
        if a is None or b is None:
            return a is b
        if isinstance(a, bool) or isinstance(b, bool):
            return type(a) is type(b) and a == b
        if isinstance(a, Number) or isinstance(b, Number):
            try:
                left, right = Decimal(str(a)), Decimal(str(b))
                if isinstance(a, int) or isinstance(b, int):
                    return left == right
                return isclose(float(left), float(right),
                               rel_tol=rel_tol, abs_tol=abs_tol)
            except (InvalidOperation, ValueError, TypeError):
                return False
        return a == b

    def equal_row(a, b):
        left, right = list(a.values()), list(b.values())
        return len(left) == len(right) and all(equal_value(x, y) for x, y in zip(left, right))

    if ordered:
        return all(equal_row(a, b) for a, b in zip(actual, expected))
    # Maximum bipartite matching avoids greedy tolerance/duplicate collisions.
    matched = {}
    def assign(index, visited):
        for other, row in enumerate(expected):
            if other not in visited and equal_row(actual[index], row):
                visited.add(other)
                if other not in matched or assign(matched[other], visited):
                    matched[other] = index
                    return True
        return False
    return all(assign(index, set()) for index in range(len(actual)))


def compare_result_sets(actual, expected, ordered=False):
    """Even an empty result must expose the requested projection width."""
    from decimal import Decimal, InvalidOperation
    if len(actual.get('columns',[])) != len(expected.get('columns',[])):
        return False
    numeric = set(expected.get('numeric_columns',[]))
    integers = set(expected.get('integer_columns',[]))
    def normalize(rows,columns):
        output=[]
        for row in rows:
            if len(row)!=len(columns):
                raise ValueError('Result projection cannot be represented without duplicate/missing columns.')
            values=[]
            for index,name in enumerate(columns):
                value=row[name]
                if value is not None and index in numeric:
                    value=Decimal(str(value))
                    if index in integers and value == value.to_integral_value():
                        value=int(value)
                values.append(value)
            output.append(dict(enumerate(values)))
        return output
    try:
        return compare_result_rows(normalize(actual.get('rows',[]),actual.get('columns',[])),
                                   normalize(expected.get('rows',[]),expected.get('columns',[])),ordered=ordered)
    except (InvalidOperation,ValueError,TypeError,KeyError):
        return False


def score_retrieval(ranked_tables, required_tables, k=7):
    """Independent reference labels, never generated SQL, define relevance."""
    required = set(required_tables)
    if not required:
        raise ValueError('Retrieval cases require nonempty independent table labels.')
    ranked = list(dict.fromkeys(ranked_tables))[:k]
    found = required.intersection(ranked)
    return {
        'reciprocal_rank': next((1 / rank for rank, name in enumerate(ranked, 1)
                                 if name in required), 0.0),
        'recall_at_k': len(found) / len(required),
        'precision_at_k': len(found) / len(ranked) if ranked else 0.0,
        'all_required_tables_found': found == required,
    }


def summarize_evaluation(records):
    """All cases, including provider/execution failures, remain in denominators."""
    import statistics
    n = len(records)
    final = sum(bool(r['final_correct']) for r in records)
    first = sum(bool(r['first_attempt_correct']) for r in records)
    retried = [r for r in records if r['retries'] > 0]
    recovered = sum(not r['first_attempt_correct'] and r['final_correct'] for r in retried)
    times = sorted(r['elapsed_s'] for r in records)
    def quantile(p):
        if not times:
            return None
        index = (len(times)-1)*p
        low = int(index)
        return times[low]+(times[min(low+1,len(times)-1)]-times[low])*(index-low)
    return {'cases':n,'first_attempt_correct':first,'final_correct':final,
            'first_attempt_execution_accuracy':first/n if n else None,
            'final_execution_accuracy':final/n if n else None,
            'retried_cases':len(retried),'retry_recovered_cases':recovered,
            'retry_recovery_rate':recovered/len(retried) if retried else None,
            'mean_latency_s':statistics.mean(times) if times else None,
            'p50_latency_s':quantile(.5),'p95_latency_s':quantile(.95)}

# ── Test Cases ────────────────────────────────────────────
# Each test has: question, expected_type, validation keywords/checks
TEST_QUERIES = [
    # --- Driver Stats ---
    {
        "question": "Who has the most race wins in F1 history?",
        "category": "Driver Stats",
        "expect_sql": True,
        "validation": ["hamilton", "105"],
    },
    {
        "question": "How many world championships has Michael Schumacher won?",
        "category": "Driver Stats",
        "expect_sql": True,
        "validation": ["schumacher", "7"],
    },
    {
        "question": "Which driver has the most pole positions?",
        "category": "Driver Stats",
        "expect_sql": True,
        "validation": ["hamilton"],
    },
    {
        "question": "List the top 5 drivers by career points",
        "category": "Driver Stats",
        "expect_sql": True,
        "validation": ["hamilton", "verstappen"],
    },

    # --- Race & Circuit Queries ---
    {
        "question": "How many races were held in 2023?",
        "category": "Race Queries",
        "expect_sql": True,
        "validation": ["22"],
    },
    {
        "question": "Show the race winners at Spa",
        "category": "Race Queries",
        "expect_sql": True,
        "validation": ["schumacher"],
    },
    {
        "question": "Which circuits are located in Italy?",
        "category": "Circuit Queries",
        "expect_sql": True,
        "validation": ["monza"],
    },
    {
        "question": "How many times has the Monaco Grand Prix been held?",
        "category": "Race Queries",
        "expect_sql": True,
        "validation": [],
    },

    # --- Team/Constructor Queries ---
    {
        "question": "Which team has won the most constructors championships?",
        "category": "Team Queries",
        "expect_sql": True,
        "validation": ["ferrari"],
    },
    {
        "question": "How many race wins does Red Bull have?",
        "category": "Team Queries",
        "expect_sql": True,
        "validation": ["red bull"],
    },

    # --- Lap Times & Pit Stops ---
    {
        "question": "What is the average pit stop duration in 2023?",
        "category": "Pit Stops",
        "expect_sql": True,
        "validation": [],
    },
    {
        "question": "What was the fastest lap time at Monza in 2023?",
        "category": "Lap Times",
        "expect_sql": True,
        "validation": [],
    },

    # --- Comparison Queries ---
    {
        "question": "Compare the number of wins between Hamilton and Verstappen",
        "category": "Comparison",
        "expect_sql": True,
        "validation": ["hamilton", "verstappen"],
    },

    # --- Historical Queries ---
    {
        "question": "Who won the first ever F1 race?",
        "category": "Historical",
        "expect_sql": True,
        "validation": ["farina"],
    },
    {
        "question": "How many different drivers have won a race?",
        "category": "Historical",
        "expect_sql": True,
        "validation": [],
    },

    # --- Qualifying ---
    {
        "question": "Who got pole position at the 2023 British Grand Prix?",
        "category": "Qualifying",
        "expect_sql": True,
        "validation": [],
    },

    # --- Sprint Results ---
    {
        "question": "How many sprint races were held in 2023?",
        "category": "Sprint",
        "expect_sql": True,
        "validation": [],
    },

    # --- Conversational (should NOT generate SQL) ---
    {
        "question": "What is DRS in Formula 1?",
        "category": "Conversational",
        "expect_sql": False,
        "validation": ["drag"],
    },
    {
        "question": "Hello, what can you do?",
        "category": "Conversational",
        "expect_sql": False,
        "validation": [],
    },

    # --- Edge Case: Name variations ---
    {
        "question": "Show results of the 2023 Sao Paulo Grand Prix",
        "category": "Edge Case",
        "expect_sql": True,
        "validation": [],
    },
]


def run_benchmark(api_url=None, output_path=None, queries=None):
    """Record keyword/result-presence smoke checks, not SQL execution accuracy.

    A fresh artifact is written for every run. The historical March result is
    never overwritten. Retry estimates require the API's agent_steps trace.
    """
    from datetime import datetime, timezone
    from pathlib import Path
    import hashlib

    api_url = api_url or API_URL
    queries = TEST_QUERIES if queries is None else queries
    results = []
    for test in queries:
        record = {**test, "status": "ERROR", "error": None, "retries": None,
                  "retry_trace_available": False, "has_results": False,
                  "sql_generated": False}
        start = time.perf_counter()
        try:
            response = requests.post(api_url, json={"message": test["question"]}, timeout=60)
            if response.status_code != 200:
                record.update(status="HTTP_ERROR", error=f"HTTP {response.status_code}")
            else:
                data = response.json()
                if not isinstance(data, dict):
                    raise ValueError("Expected a JSON object response")
                record["response"] = data
                answer = (data.get("answer") or "").lower()
                sql = data.get("sql") or ""
                result_data = data.get("results") or {}
                rows = result_data.get("rows") or []
                steps = data.get("agent_steps")
                if isinstance(steps, list):
                    record["retry_trace_available"] = True
                    record["retries"] = sum(
                        1 for step in steps
                        if isinstance(step, dict) and step.get("node") == "retry_sql"
                    )
                record["sql_generated"] = bool(sql.strip())
                record["has_results"] = bool(rows) if test["expect_sql"] else True
                record["error"] = data.get("error")
                record["failed_keywords"] = [
                    keyword for keyword in test["validation"]
                    if keyword.lower() not in answer
                ]
                if record["error"]:
                    record["status"] = "ERROR"
                elif record["sql_generated"] != test["expect_sql"]:
                    record["status"] = "WRONG_TYPE"
                elif test["expect_sql"] and not rows:
                    record["status"] = "NO_RESULTS"
                elif record["failed_keywords"]:
                    record["status"] = "VALIDATION_FAIL"
                else:
                    record["status"] = "PASS"
        except requests.exceptions.Timeout:
            record.update(status="TIMEOUT", error="Request timed out")
        except (ValueError, TypeError, AttributeError) as exc:
            record.update(status="RESPONSE_ERROR", error=str(exc))
        except requests.exceptions.RequestException as exc:
            record.update(status="HTTP_ERROR", error=str(exc))
        finally:
            record["time"] = round(time.perf_counter() - start, 6)
            results.append(record)
        print(f"{record['status']}: {test['question']} ({record['time']:.2f}s)")

    sql_cases = [r for r in results if r["expect_sql"]]
    passed = sum(r["status"] == "PASS" for r in results)
    sql_passed = sum(r["status"] == "PASS" for r in sql_cases)
    retry_cases = [r for r in sql_cases if r["retries"] is not None and r["retries"] > 0]
    retry_passed = sum(r["status"] == "PASS" for r in retry_cases)
    times = [r["time"] for r in results]
    def percentage(numerator, denominator):
        return round(100 * numerator / denominator, 1) if denominator else None

    now = datetime.now(timezone.utc)
    output = {
        "schema_version": 2,
        "timestamp": now.isoformat(),
        "api_url": api_url,
        "methodology": "SQL generation, nonempty results and answer-keyword smoke checks; not reference-result equivalence",
        "suite_sha256": hashlib.sha256(
            json.dumps(queries, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "benchmark_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "total_queries": len(results),
        "checks_passed": passed,
        "check_pass_rate": percentage(passed, len(results)),
        "sql_queries": len(sql_cases),
        "sql_checks_passed": sql_passed,
        "sql_check_pass_rate": percentage(sql_passed, len(sql_cases)),
        "sql_cases_with_retry_trace": sum(r["retry_trace_available"] for r in sql_cases),
        "sql_checks_passed_without_retry": sum(
            r["status"] == "PASS" and r["retries"] == 0 for r in sql_cases
        ),
        "avg_response_time": round(sum(times) / len(times), 2) if times else None,
        "min_response_time": round(min(times), 2) if times else None,
        "max_response_time": round(max(times), 2) if times else None,
        "retries_needed": len(retry_cases),
        "retry_checks_passed": retry_passed,
        "retry_success_rate": percentage(retry_passed, len(retry_cases)),
        "results": results,
    }
    output_path = Path(output_path) if output_path else (
        Path("artifacts/benchmarks") / f"{now.strftime('%Y%m%dT%H%M%S%fZ')}.json"
    )
    # Historical measurements must remain available even with an explicit path.
    historical = Path(__file__).with_name("benchmark_results.json").resolve()
    if output_path.resolve() == historical:
        raise ValueError("The historical benchmark artifact is immutable; choose a new output path.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8") as handle:
        json.dump(output, handle, indent=2, ensure_ascii=False, allow_nan=False)
    print(f"SQL smoke checks: {sql_passed}/{len(sql_cases)}; retry cases: {len(retry_cases)}")
    print(f"Results saved to: {output_path}")
    return output


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run F1 API smoke checks and preserve a fresh artifact.")
    parser.add_argument("--api-url", default=API_URL)
    parser.add_argument("--output", help="New JSON path; existing files are never overwritten.")
    args = parser.parse_args()
    run_benchmark(api_url=args.api_url, output_path=args.output)
