# GrowthScope — Sprint 01: GA4 data-discovery exploration

Read-only SQL used to learn the real shape of the GA4 export **before** any
metric, schema, or model assumes it. Everything here targets Google's public
sample:

```text
bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*
```

- Google Merchandise Store web stream, **obfuscated** sample covering
  2020-11-01 … 2021-01-31. Placeholder values (`<Other>`, NULL, `''`) are
  part of the data, not corruption.
- Every statement is a `SELECT` (no DDL/DML, nothing is written or exported),
  so all files are safe to rerun.

> **STATUS: UNVERIFIED.**
> BigQuery was not available in the environment where these files were
> written. **No result, count, or byte figure in this folder was produced by
> an actual run — none exists here by design.** The files are instructions
> until somebody runs them; running them is the remaining work of Sprint 01.
> Do not quote any number as real until it comes from a run with a Job ID.

---

## Execution order

| # | File | Question it answers | Query grains |
|---|------|--------------------|--------------|
| 00 | `00_project_settings.sql` | Which shards exist in the window? How do I run/price everything safely? | 1 row per shard (section C) |
| 01 | `01_event_inventory.sql` | Which events exist, how often, and which are unexpected? | per event name |
| 02 | `02_daily_event_volume.sql` | How big is each day, and how do users distribute across events? | per day / per user bucket |
| 03 | `03_user_identification.sql` | Are `user_pseudo_id`, `user_id`, `user_first_touch_timestamp` usable? | summary rows |
| 04 | `04_event_parameters.sql` | Which `event_params` keys exist and how are values stored? | per param key / per event |
| 05 | `05_funnel_event_audit.sql` | Do the 13 journey events actually occur? (presence, NOT conversion) | per expected event |
| 06 | `06_purchase_revenue_audit.sql` | Which revenue fields are populated, in which currency, and are transactions duplicated? | summary + per transaction |
| 07 | `07_session_feasibility.sql` | Can sessions be reconstructed, and is the composite key really needed? | summary rows |

Run **00 → 01 → … → 07**. 00 is a preflight (cost, setup, shard check) — run
its section C before anything else. Files 01–07 are independent of each other
(shared conventions only), so a single file can be rerun alone.

## Window convention (single source of truth)

- Default window: **2020-11-01 … 2020-11-03** (3 days).
- Predicate, in every query, exactly once:

  ```sql
  _TABLE_SUFFIX BETWEEN '20201101' AND '20201103' -- [WINDOW]
  ```

- To change the window, find/replace **both** literals in a file; do not add a
  second date filter.
- Why a literal: only a **constant expression** on `_TABLE_SUFFIX` prunes the
  shards. A `DECLARE`d variable or an `event_date` filter does **not** — the
  whole dataset gets read and billed (`00_project_settings.sql`, section F).
- After changing the window, rerun the 00 preflight (the range may include
  days with no shard) and dry-run before running.

## Cost model (read before running anything)

1. On-demand BigQuery bills **bytes read**. Costs are driven by how many
   shards match `_TABLE_SUFFIX` and how many columns are projected.
2. **Dry-run first** — it validates the SQL and estimates bytes free of
   charge. Console: the estimate appears above the editor. CLI:
   `bq query --use_legacy_sql=false --dry_run "<sql>"`.
3. Set **Maximum bytes billed** on every run (console: Query settings;
   CLI: `--maximum_bytes_billed=N`). If the estimate exceeds the cap, the
   query fails **without** being charged.
4. **Wildcard queries are never answered from cache** (official docs): every
   rerun is billed again, even with identical SQL.
5. The **Sandbox** (no card required) covers this exploration easily:
   1 TiB processed/month, no DML needed, Google's sample guide points to it.
6. After a run, check the job's *bytes processed* against your expectation —
   a number near the whole dataset size means the suffix filter was wrong.

## How to run

**A. BigQuery console (recommended — shows every statement's result)**

1. Open <https://console.cloud.google.com/bigquery> (Sandbox is fine).
2. Paste a file's contents into the editor (all statements at once is OK).
3. Set *Maximum bytes billed* in Query settings, then **Run**.
4. The console shows one result set per statement — copy each one into the
   results log (below). Check *Job information* for Job ID and bytes.

**B. `bq` CLI** (full setup in `00_project_settings.sql`, section E)

```bash
bq query --use_legacy_sql=false --dry_run \
  "$(cat sql/exploration/01_event_inventory.sql)"

bq query --use_legacy_sql=false \
  --maximum_bytes_billed=1000000000 \
  "$(cat sql/exploration/01_event_inventory.sql)"
```

PowerShell: replace `"$(cat …)"` with `(Get-Content sql\exploration\01_event_inventory.sql -Raw)`.

Note: `bq query` displays at most `--max_rows` rows per result (default 100) —
raise it (e.g. `--max_rows=1000`) when a result set can exceed 100 rows, or
read the full result in the console.

**C. Python client**

```python
from google.cloud import bigquery

client = bigquery.Client(project="YOUR_PROJECT_ID")
sql = open("sql/exploration/01_event_inventory.sql", encoding="utf-8").read()
job = client.query(
    sql,
    job_config=bigquery.QueryJobConfig(maximum_bytes_billed=1_000_000_000),
)
rows = list(job.result())          # rows of the LAST statement only
print(job.total_bytes_processed)   # actual bytes read
```

Multi-statement caveat: the console and `bq query` show every statement's
result (bq prints each step); the REST API / client `job.result()` returns
**only the last statement's rows**. For per-statement results in Python, run
one statement per call (split the file) or use the console.

## Recording results (the results log)

The queries are only half of Sprint 01; the measured answers are the other
half. This folder intentionally ships **no results file** — the team creates
the log when it first runs the queries (suggested location:
`sql/exploration/RESULTS.md`, or wherever Sprint 01 notes live).

Template — one row per query result set:

```text
FILE / QUERY      | WINDOW                | RUN (date, who) | JOB ID | BYTES PROCESSED | RESULT SUMMARY | NOTES
01 Q1             | 20201101–20201103     | 2026-…          | …      | …               | …              | …
```

Rules for the log:

- Copy numbers only from the returned rows (or the job statistics). Never
  fill in an expected value.
- Keep the Job ID — it is the proof a number came from a real run.
- Label every finding: *obfuscated sample, window 2020-11-01…03*, so nobody
  reads it as a real-store fact.
- Empty result sets are findings too ("no duplicate transaction in window"),
  record them explicitly.

## Conventions inside every file

- Header block: purpose, tables, scan risk, output grain, caveats,
  `READ-ONLY`, `STATUS`.
- Uppercase SQL keywords, 2-space indent, one CTE per logical step.
- No `SELECT *` over the event tables; only needed columns are projected.
- Parameter extraction via correlated scalar subquery
  `(SELECT value.int_value FROM UNNEST(event_params) WHERE key = '…')` — never
  `JOIN … UNNEST` for counting, which fans out rows and inflates counts
  (patterns in `04_event_parameters.sql`).
- Session key is always the composite
  `(user_pseudo_id | ga_session_id)` — `ga_session_id` alone is shared across
  users (proof in `07_session_feasibility.sql` Q2–Q3).
- Counts are never called "conversions": 05 is a **presence audit**; funnel
  rates are Sprint 02 work.
