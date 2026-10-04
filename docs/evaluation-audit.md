# Evaluation and execution audit — 4 October 2026

## What the historical artifact supports

The unchanged `tests/benchmark_results.json`, recorded on 25 March 2026,
contains 20 questions: 18 SQL questions and two conversational questions.
Fifteen SQL-question cases passed generation, nonempty-result and answer-keyword
checks. This is a smoke-check result, not ground-truth execution accuracy.
Empty keyword lists also make some cases substantially weaker than others.

The benchmark read `steps`, while the API returned `agent_steps`. Consequently,
its zero retry counts cannot establish an absence of retries. Its default
100% retry-success field has a zero denominator and is not an estimate.
The final pass count did not exclude retry passes and therefore cannot be
called first-attempt accuracy. Timeout/exception timings were excluded from
the accumulated latency numerator; historical latency fields are not retained
as performance claims. Raw per-case times remain available as historical data.

The original artifact is preserved rather than retrospectively recomputed:
the saved records lack the traces and response tables required for a reliable
reconstruction. A new run is required to obtain corrected measurements.

## Corrected software behavior

- Benchmark v2 reads `agent_steps`, distinguishes unavailable traces from zero
  observed retries, includes failure/timeout durations, and reports `null` for
  empty denominators. Its pass metrics are named smoke checks.
- New artifacts retain question definitions, raw API responses, timestamps,
  suite/code hashes and per-case timings; existing files and the original
  artifact cannot be overwritten by the benchmark command.
- Reciprocal rank uses the best retrieved relevant table, rather than the
  first table listed in generated SQL. A single query has RR; MRR requires
  a mean over a defined query set. The API retains `mrr` for compatibility
  and adds `reciprocal_rank` with an explicit proxy definition.
- SQL table extraction uses parsed scopes so qualified names and CTE aliases
  are handled correctly. Relevance still comes from generated SQL; a wrong
  query can give misleadingly favorable diagnostics.
- The legacy `faithfulness_score` API key is retained for compatibility.
  Its meaning is substring coverage of eligible values from the first five
  result rows, excluding ID/URL fields and very short values. It does not
  measure semantic correctness. No eligible values means `null`, not 100%.
- The UI describes these proxies and renders unavailable values explicitly.

## Historical retrieval claims

The report describes schema enrichment, application-table exclusion and
co-occurrence rules. These are implementation changes. The historical
`0.12 → 0.25 → 0.67` aggregate does not have a recovered, reproducible
fixed-set basis; the displayed iteration rows do not directly establish it.
The ranking bug and generated-SQL relevance proxy further limit interpretation.
No numerical retrieval improvement is claimed in current public wording.

## Execution controls and limits

The agent and connector use the same SQLGlot-based MySQL query policy. It
rejects multiple statements, side-effect statements, SELECT INTO, locking,
session variables, executable comments/hints and unknown functions. Supported
SELECT/CTE/UNION queries receive an outer row cap, and the API shows the query
actually executed. TLS-enabled pool and fallback connections both verify
certificate and hostname, with a configurable CA bundle.

This does not establish database-level read-only permissions, protection from
every database extension, bounded query CPU time or secure multi-user chat
access. The existing account also writes conversation history. Separate query
credentials, appropriate grants, server-side resource limits and authenticated
conversation access remain deployment requirements, outside this repair.

## Evidence boundary

Run `python -m pytest -q` and `node tests/metric_bar_check.cjs` to reproduce
offline regression checks. External HTTP/database operations are simulated
at their boundaries; no model API or live database is required. These are
software checks, not a new model evaluation, an industrial benchmark or a
live deployment certification.

To support a future accuracy claim, preserve a fixed database snapshot,
independently reviewed reference SQL/result tables, explicit ordering and
empty-result rules, a held-out query set, model/prompt/settings identifiers,
raw outputs and a rerunnable evaluator. Regression fixtures must not be
presented as held-out model performance.
