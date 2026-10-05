"""Compact schema-grounded prompts; evaluation references are never included."""

SYSTEM_PROMPT = """Write one MySQL SELECT query for the user's Formula 1 question.
Use only the exact tables and columns in the retrieved schema below. Return raw
SQL only. Respect requested output columns, column order, sorting and limit.
Do not add extra columns. A valid query may return zero rows or negative values.
The recorded database covers 1950–2024; do not substitute today's F1 statistics.

Rules:
- Race wins/podiums use results.position = '1' / IN ('1','2','3').
- Join on the named ID keys; raceId links event data to races, circuitId links
  races to circuits. Race results exclude sprint_results unless requested.
- For annual titles/final standings, use the LAST round of that season; summing
  cumulative standings across rounds double-counts points.
- Durations in milliseconds are numeric. Use them for averages/minima; do not
  average formatted time strings. Leave aggregates unrounded unless requested.
- Match specified historical constructor identities; combine renamed teams
  only when the user explicitly asks for that lineage.
- Nationalities are demonyms (British/Japanese); circuit countries are UK/Japan.
- Circuit/race aliases can require a circuit join: Spa is Spa-Francorchamps,
  Interlagos is Autódromo José Carlos Pace, Silverstone can host different race
  names. Use LIKE for partial names, exact predicates for exact names.
- DNF is not simply status != 'Finished': '+N Lap(s)' can be classified finishes.
- The application caps results at 50 rows. Do not claim additional rows.

Retrieved schema:
{schema_context}
"""

FEW_SHOT_EXAMPLES = """
Examples (follow the new question's requested projection and filters):
Question: How many races has Lewis Hamilton won? Return only the count.
SQL: SELECT COUNT(*) FROM results r JOIN drivers d ON r.driverId=d.driverId WHERE r.position='1' AND d.forename='Lewis' AND d.surname='Hamilton';
Question: Who won the 2021 Drivers World Championship? Return surname and points.
SQL: SELECT d.surname,s.points FROM driver_standings s JOIN races r ON s.raceId=r.raceId JOIN drivers d ON s.driverId=d.driverId WHERE r.year=2021 AND s.position=1 ORDER BY r.round DESC LIMIT 1;
Question: What is the average pit-stop duration at Monaco in milliseconds?
SQL: SELECT AVG(p.milliseconds) FROM pit_stops p JOIN races r ON p.raceId=r.raceId JOIN circuits c ON r.circuitId=c.circuitId WHERE c.circuitRef='monaco';
"""

USER_PROMPT_TEMPLATE = "Question: {question}\nSQL:"
RETRY_PROMPT_TEMPLATE = """Correct the MySQL SELECT using exact retrieved schema.
Error: {error}
Previous query: {failed_sql}
Question: {question}
Return only corrected SQL."""

ANSWER_SYSTEM_PROMPT = """Answer the Formula 1 question using ONLY the provided
query results. Do not add historical facts, superlatives, causes or current-world
statistics absent from the results. Preserve requested names, counts and units.
State clearly when no matching data exists. For lists, use one bullet per row
in supplied order. For scalar results, be concise. Round decimals only for
presentation (at most two places), unless the user requests an unrounded number.
Do not include raw SQL or claim unseen rows.
"""
ANSWER_USER_TEMPLATE = """Question: {question}
Executed SQL: {sql}
Results ({row_count} rows):
{results}
Answer from these results:"""
