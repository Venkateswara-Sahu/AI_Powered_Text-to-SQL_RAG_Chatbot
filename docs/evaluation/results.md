# F1 reference-result evaluation — 4 October 2026

The real nine-node agent was evaluated on **40 separate SQL questions** after
20 development questions and a frozen implementation. Reference SQL/results
and required-table labels were independently reviewed and withheld from the
application model. Every question remains in the denominator.

| Measure | Result | Meaning |
| --- | ---: | --- |
| First-attempt reference-result matches | 39/40 (97.5%) | Initial SQL-generation attempt produced a matching executed result; failed/unsafe generation counts as failure |
| Final reference-result matches | 39/40 (97.5%) | Final query matched the reference |
| Natural SQL corrections | 0/40 | Graph correction nodes; not provider HTTP retries |
| Dense MRR@7, plain → enriched | 0.678 → 0.888 | Independent required-table labels; same embedding model and k |
| Macro Recall@7, plain → enriched | 0.838 → 0.950 | Mean fraction of all required tables retrieved |
| All-required dense coverage, plain → enriched | 65.0% → 87.5% | Questions with every required table in top seven |
| Augmented-context recall / full coverage | 1.000 / 100.0% | Includes co-occurrence rule injection; no arbitrary MRR assigned |
| Mean / median / p95 elapsed | 46.64s / 48.17s / 50.31s | Includes free-tier token pacing and model calls |
| Separate controlled invalid-column probes | 5/5 recovered | Five development cases, one injected first-execution error each |

Natural-query retry recovery is undefined because no ordinary evaluation query retried.
The five controlled probes establish the exercised correction path for this
fault type; they are not combined with ordinary accuracy or used to estimate
natural-query retry success. Development results were 20/20 first and final
matches, and are kept separate from evaluation.

## What changed and what this establishes

Before freezing, valid empty results and negative coordinates stopped causing
unjustified rewrites; failed generation consumed the attempt budget; SQL and
execution traces became complete. The SQL prompt now uses compact retrieved
columns/keys instead of repeated rich prose plus an unrelated global schema.
The evaluation client disables implicit SDK retries and records calls, waits,
usage, failures and exact executed SQL. These changes have 54 offline regression
tests; they were not tuned against the completed evaluation results.

This is an authored single-domain study, with explicit projection/order
contracts and related development/evaluation query patterns. Result equivalence
on one snapshot does not prove SQL semantics on all data, arbitrary-question
accuracy or complete natural-language answer faithfulness. Rich-versus-plain
retrieval is a current controlled comparison, not a reconstruction of the old
0.12-to-0.67 aggregate or proof that enrichment caused the execution score.

The isolated snapshot contains **701,433 records in 14 F1 tables**, races
1950–2024. A SELECT-only local MySQL 8.4 account and 15-second query cap were
verified. This does not establish production TiDB grants, API authentication,
multi-user conversation isolation, service availability or deployment readiness.
The full graph was called directly with fresh history; HTTP and conversation
storage overhead were excluded. Latency includes deliberate free-tier pacing,
so it is not a production speed or throughput claim. This October re-evaluation
must not be represented as an internship-era measurement.

## Observed failures and subsequent repairs

E33 generated an exact surname predicate for `Perez`, but the recorded surname
is `Pérez`: it returned NULL instead of the reference 190 race-result points.
The query executed without an SQL error, so the correction path did not fire.
E05 and E39 had correct SQL results, but their prose answers received only the
first 20 rows and omitted one race / two circuits, respectively. The omissions
were disclosed, but the requested lists were incomplete.

On 5 October, after this frozen run, physical `drivers.forename`/`surname` literal equalities
were given explicit accent/case-insensitive Unicode comparison. The original
SQL is validated before transformation; stable IDs, other tables, CTE shadows
and LIKE patterns retain their behavior. Large lists now render every returned
row directly, preserving order and avoiding model input/output truncation.
The supported collation is documented by [TiDB](https://docs.pingcap.com/tidb/stable/character-set-and-collation/).
The repaired branch has 68 passing regression tests. A separate
[saved-SQL replay](post-evaluation-replay.json) records all 40 old generated
queries matching after repair, plus complete 21/22-row answers and constant
collation probes on local MySQL and TLS-verified TiDB. This makes NO new model
queries and does not replace the original **39/40 (97.5%)** generative score.
The evaluated implementation hash below remains the basis of the CV claim.

## Auditable evidence

- [Complete raw evaluation](evaluation.json): SHA-256 `935ee3b1b59df5b3a00f46f334cd77a3f8bae60e933db247bdc3794495f039a3`.
- Frozen implementation: `d71e49c45acf9b5164aea1cc47610b9dc46d6959`.
- Code hash: `04fa8beb20193f42335d729541bf01fc6f1eb53e264229c826e8dce9f62d5bd6`.
- Suite hash: `0d663c9ef00870fa98ec63ad62df734eb02a9b34b2ab4afa300c90e39af99a78`.
- Frozen reference artifact hash: `d6ee0d173b814bc7f9fa34f872d61bede463a1525d40e282d60dacf22af020d3`.
- Original backup hash: `4235e1e701350ba9b294cb8b11b7dd7fa27324e5f9dbcd193095a450cdbe7c4a`.
- [Reference contracts and results](references.json).
- [Development artifact](development.json) and [controlled probes](retry-probes.json), unchanged; their earlier SDK/trace caveats are retained in the protocol.
- [Full protocol and reproduction](../ground-truth-evaluation.md).
- [Historical artifact audit](../evaluation-audit.md); the March smoke results remain unchanged.
