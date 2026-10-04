# Ground-truth evaluation protocol

This evaluates the real nine-node SQL agent on a frozen copy of the original
F1 project database. It replaces keyword checks as the basis for current
execution-correctness claims. It does not reconstruct historical measurements.

## Data and separation

- Source: private project SQL backup recorded 21 May 2026, SHA-256
  `4235e1e701350ba9b294cb8b11b7dd7fa27324e5f9dbcd193095a450cdbe7c4a`.
- Restore only the 14 F1 tables: 701,433 records, races spanning 1950–2024.
  Conversation/message tables are excluded and are never published.
- F1-only SQL SHA-256:
  `7e07f7806742dcea6007933d08212500f7e6bd9951f76251b8f15ce2b6f53368`.
- Evaluation executes against isolated MySQL 8.4 on localhost, with a
  SELECT-only account and 15-second server query limit. This verifies the
  isolated evaluation boundary, not production TiDB grants or API authentication.
- `tests/reference_cases.py` defines 20 development and 40 evaluation SQL
  question contracts. The 40 are separate questions, but include related query
  patterns; this is a small, authored, single-domain evaluation, not an external
  benchmark or a claim of wholly unseen reasoning tasks.
- Reference SQL, required tables, and expected result rows are never supplied
  to the application model. Each query starts with empty conversation history.
- All 60 SQL contracts were reviewed independently; 12 alternative SQL
  formulations were executed to cross-check joins, standings, ties, NULLs,
  distinct counts, and race-winning predicates. The frozen reference artifact
  is [references.json](evaluation/references.json).

## Measurement contracts

**First-attempt correctness:** the first actual execution must succeed and
match the reference result. Unsafe/failed generation counts as incorrect.

**Final correctness:** the agent's final execution must succeed and match the
reference result. Every question stays in the denominator, including provider,
generation and execution failures. This measures result equivalence, not SQL
string equality or semantic correctness of every narrative claim.

**Result equivalence:** aliases may differ; the requested projection width and
column order must agree. Integer reference columns compare exactly. Noninteger
numerical differences use absolute tolerance 0.000001 with zero relative
tolerance. Numeric metadata distinguishes serialized Decimal values from real
strings. NULL, zero and empty sets are distinct; duplicates retain multiplicity.
Specified row order matters; unspecified row order is matched as a multiset.
Empty results still require the correct projection width. Result matching on
one fixed database does not prove universal semantic equivalence of SQL.

**Retries:** only `retry_sql` graph nodes count as SQL correction attempts.
The normal budget is initial generation plus one correction. Recovery rate
uses retried questions as its denominator; no observed retries yields no rate.
Provider HTTP retries are logged separately and do not count as SQL correction.

**Retrieval:** independently authored required-table labels define relevance.
Dense MRR@7 is the mean reciprocal rank of the first required table in the
top seven. Macro Recall@7 measures the fraction of *all* required tables found,
and all-required coverage checks full schema coverage per question. Compare
plain and semantically enriched dense retrieval with identical schema, sample
rows, embedding model, FAISS index type and k. The plain variant disables
enrichment/co-occurrence in current code; it is not the original historical
retriever. Augmented context reports recall, precision and all-required
coverage, without assigning semantic rank to rule-injected tables.

**Latency:** wall-clock time covers the complete agent run, including failures,
database execution, model calls, quota pacing and explicit provider retries.
The separate inter-question pause is excluded. This is free-tier evaluation
latency, not unconstrained production throughput. Per-call usage, waits and
provider fingerprints are retained. Groq's documented free-tier limits for
the configured model are 8,000 tokens/minute and 200,000 tokens/day; the observed
response headers confirm the minute limit. See
[Groq rate limits](https://console.groq.com/docs/rate-limits).

## Fixes made before the evaluation freeze

- Valid empty query results and negative geographical values no longer trigger
  an unsupported query rewrite.
- Failed/unsafe initial generation consumes the attempt budget.
- Trace entries retain complete generated/executed SQL and each execution's
  result, allowing first/final correctness to be assessed independently.
- Retrieval still indexes rich descriptions. Generation receives compact exact
  names/types/keys and a shorter prompt, rather than repeated embedding prose
  plus an unrelated full schema. Answer instructions prohibit facts absent from
  supplied query results.
- The evaluator preserves numerical serialization, empty result shapes,
  duplicate counts and provider-failure evidence correctly.

## Reproduction

Use Python 3.12 and the recorded evaluation dependency versions. Install the
application requirements in an isolated virtual environment. Prepare a local
copy of the original SQL backup; the private backup and production credentials
are intentionally not committed.

```powershell
docker run --name codex-f1-eval-20261004 --memory=2g --cpus=2 `
  -p 127.0.0.1:33070:3306 -e MYSQL_ROOT_PASSWORD=f1-local-evaluation-only `
  -e MYSQL_DATABASE=f1db -d mysql@sha256:6ea90827b1100f8f2ae306a539f86d2c264a26ed435a2a9f75551dd5c3aeb242
python tests/prepare_snapshot.py C:/private/f1db_backup.sql
python tests/evaluate.py --check-references --output artifacts/benchmarks/reference-check-new.json
$env:PYTHONHASHSEED='0'
python tests/evaluate.py --split dev --credentials C:/private/.env --output artifacts/benchmarks/dev-new.json
python tests/evaluate.py --split dev --retry-probe --credentials C:/private/.env --output artifacts/benchmarks/retry-probe-new.json
# Freeze implementation and references before this command:
python tests/evaluate.py --split eval --credentials C:/private/.env --output artifacts/benchmarks/eval-new.json
```

The supplied credential file contributes only the Groq key/model; all database
settings are overridden to the localhost SELECT-only account. Every run checks
all 14 table hashes and compares current reference results/types with the frozen
artifact before making model calls. Run metadata includes code, suite, schema,
reference-artifact and prompt hashes. Code changes during a run abort its final
artifact. JSONL progress is flushed after every question; existing artifacts
cannot be overwritten. An interrupted/provider-quota run is not reported as a
complete-set estimate.

The localhost evaluation password is deliberately nonsecret, bound to the
temporary container. Stop/remove only this specifically named container when
finished; never point restoration at production or publish a production key.

## Controlled retry probes and development artifacts

Five development questions were also tested with one nonexistent projection
column injected into their first database execution. The real model received
the actual MySQL error through the unchanged graph correction path. All five
corrected queries matched their reference results. This is **5/5 controlled
invalid-column recoveries**, not a natural-query retry-success estimate. These
cases are never combined with the 20 development or 40 evaluation accuracy
denominators.

The [development artifact](evaluation/development.json) records 20/20 first and
final result matches. The [controlled-probe artifact](evaluation/retry-probes.json)
records the five distinct injected failures and corrections. Both are preserved
unchanged. These early runs predate a benchmark-client fix: copying the
LangChain wrapper left its SDK client at two implicit retries with no explicit
timeout. No provider error is recorded, but those runs cannot establish that
implicit SDK retries were disabled; their latencies are not production claims.
Failed probe traces also retain the injected SQL before the connector's outer
LIMIT rewrite. The final evaluator constructs a fresh SDK client with zero
implicit retries and a 60-second timeout; failed executions now retain the
exact capped SQL. Neither fix changes the saved result-equivalence/recovery
counts. Recorded development results were replayed against the final comparator.
