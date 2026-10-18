# GrowthScope — Data Quality Audit

**Sprint 01 — Project Foundation & Data Discovery**
**Subject:** `bigquery-public-data.ga4_obfuscated_sample_ecommerce`
**Author role:** Data Quality & Analytics QA

| Item | Value |
|---|---|
| Dataset under audit | `bigquery-public-data.ga4_obfuscated_sample_ecommerce` (Google public GA4 obfuscated sample) |
| Authoring environment | Windows, Python 3.12.10, pandas 3.0.6, pytest 9.1.1 |
| Live warehouse access | **None** — no `gcloud`/`bq` binary, no credentials, BigQuery REST returns HTTP 401 |
| Code audited | `src/growthscope/quality/` (validation library), `sql/exploration/*.sql` (read-only exploration queries) |
| Test command | `.\.venv\Scripts\python.exe -m pytest tests` |
| Latest local result | `122 passed, 1 skipped in 0.44s` — 123 collected: 116 quality checks + 7 static SQL checks (only the duration varies between runs) |
| Audit date | Sprint 01 — 2026-10-19 (authoring environment date) |

> **Read this first.** This document separates three very different things that are
> easy to blur in a hackathon: (1) **what the documentation says** about GA4 and this
> dataset, (2) **what the local test suite proves about our code**, and (3) **what
> nobody has been able to check about the real data**, because the warehouse is
> unreachable from this environment. Every claim below carries one of the four
> markers in §1. No number in this document was produced by a query against the real
> dataset, because no such query was possible. Nothing here is inferred from the
> synthetic test fixtures except the behaviour of the code.

---

## 1. Verification legend

| Marker | Meaning | What it is worth |
|---|---|---|
| `[VERIFIED — local test]` | Proven by code that runs in this repository (`pytest`), on **synthetic** fixtures. Proves the *check* works, never a fact about the dataset. | Strong evidence about our software, no evidence about GA4. |
| `[DOCUMENTED]` | Stated in Google's documentation (or another external source), collected in `docs/dataset_research.md` with source IDs. Not executed here; no query confirmed it. | Trustworthy provenance, still unconfirmed in this environment. |
| `[BLOCKED — NO BIGQUERY ACCESS]` | Cannot be answered in the authoring environment: needs credentials or a warehouse connection. The exact query needed is given in §6. | An open question with a defined next action, not an opinion. |
| `[UNVERIFIED]` | Plausible, consistent with documentation, but no source and no query confirms it. Must not be presented as fact. | A hypothesis to test. |

`[VERIFIED — local test]` never upgrades a statement about GA4 into a verified
finding. A green test suite proves that `check_date_coverage` detects a gap; it does
not prove that the sample dataset contains one.

## 2. Severity definitions

| Severity | Definition (used consistently below) |
|---|---|
| **Critical** | The data cannot be used at all for the stated purpose: every metric derived from it is unverifiable and no local workaround exists. |
| **High** | A published metric can be **silently wrong** (double-counted, merged, mis-dated, mis-attributed) unless an explicit mitigating rule is applied *before* the metric ships. |
| **Medium** | A published metric is degraded or a slice of the data is unusable; the metric may still ship with an explicit caveat, a documented exclusion, or a clearly-labelled denominator change. |
| **Low** | An analytical limitation that affects interpretation (categories, comparability) but does not make a number incorrect. |
| **Informational** | A documented property of the dataset or the product that users must be told about; no defect exists and no code mitigation is required. |

Severity is assigned from **impact × evidence**: the potential harm of being wrong,
discounted by how likely and how observable the problem is. Where the impact would be
High but the evidence is still missing, the finding is marked Medium and says so
explicitly — a finding is not promoted to High just to look thorough.

---

## 3. Method — what was actually executed

### 3.1 Executed here

1. **Built a validation library** in `src/growthscope/quality/` (10 checks + 1
   conversion helper). Every check takes a **small aggregate DataFrame** produced by
   an exploration query — never the raw export — and returns an immutable
   `CheckResult(name, passed, severity, metric_value, threshold, message, evidence)`.
   Rationale: an aggregate-level check is cheap (no full-export transfer), catches the
   bugs that actually break the product (fan-out joins, a lost `GROUP BY` grain, a
   non-nested funnel), and — decisively in this environment — is **testable without
   cloud access**.
2. **Ran the test suite**: `.\.venv\Scripts\python.exe -m pytest tests` →
   `122 passed, 1 skipped in 0.44s` (the duration varies per run; the counts do not).
   The single skip is
   `tests/test_quality_checks.py::TestChecksOnMultipleAggregates::test_real_aggregate_fixtures_load_or_skip`,
   which is *supposed* to skip: the repository ships no real aggregate under
   `tests/fixtures/` (see `tests/fixtures/README.md`).
3. **Statically validated the exploration SQL** (`tests/test_sql_queries.py`, 7
   tests, all passing against the 8 `.sql` files currently in `sql/exploration/`):
   every file has a `Purpose` + `Caveats` header, no bare `SELECT *`, every
   `events_*` wildcard read is accompanied by a `_TABLE_SUFFIX` filter, no
   `INSERT/UPDATE/DELETE/CREATE/DROP/MERGE/TRUNCATE` statement appears (comments
   stripped before the check), and no file is empty. This is a **contract test on the
   queries**, not a data test: it guarantees the scripts stay read-only and cheap to
   run.
4. **Reviewed the project's own research artefacts** (`docs/dataset_research.md`,
   `docs/data_dictionary.md`, `docs/metric_dictionary.md`) for documented GA4
   semantics, and cross-checked the claims a metric will depend on. Where those
   documents already flag a claim as unverified, this audit keeps that status.

### 3.2 Not executed, and why

* **No query was run against the dataset.** `gcloud` and `bq` are absent from the
  environment, no service-account credentials exist, and an unauthenticated call to
  the BigQuery REST API returns HTTP 401. Every dataset-level statement in §4 is
  therefore `[BLOCKED — NO BIGQUERY ACCESS]` or `[DOCUMENTED]`; §6 lists the exact
  queries that would close each one.
* **No real aggregate was inspected**, so no NULL rate, duplicate rate, currency
  count, date gap or event-mix number is quoted anywhere in this document. Quoting
  one would be fabrication.

### 3.3 Honest limitations of this audit

* The checks validate **aggregates**, not the raw export. A defect that only exists
  at event grain (e.g. a duplicated upload bundle) is out of their reach by design.
* The checks are only as good as the queries that feed them; the static SQL tests
  reduce, but cannot eliminate, that risk.
* The library was written before any real result was seen, so its thresholds are
  deliberate defaults (strict), not calibrated to observed data. Calibration is a
  post-access task (§6, step 1).

---

## 4. Findings register

The register is grouped by theme, not by severity: (A) access and coverage,
(B) identifier completeness, (C) event and purchase integrity, (D) semantics that
change a number's meaning. "Check" column names refer to
`src/growthscope/quality/checks.py`; test references are to
`tests/test_quality_checks.py`.

**A. Access, coverage, schema**

| ID | Finding | Evidence | Impact on downstream metric/product | Severity | Mitigation | Verification status |
|---|---|---|---|---|---|---|
| DQ-01 | **Dataset cannot be queried from the authoring environment.** No `gcloud`/`bq`, no credentials; BigQuery REST returns HTTP 401. Every dataset-level claim in this repository is documentation-derived, not measured. | Absent tooling and the 401 response recorded in `docs/dataset_research.md` (source R1 is a documentation page, not a query result). No query output exists anywhere in the repo. | GrowthScope's headline claim ("computed on the public GA4 sample") is **unverifiable here**: a judge asking "show me the query output" cannot be satisfied. Metrics must therefore be demoed from a path that is explicitly labelled (replay/synthetic) until access exists, and no screenshot may imply live queries. | **Critical** (for verification, *not* a defect of the dataset) | Keep all exploration SQL committed and review-ready (`sql/exploration/00_project_settings.sql` documents the preflight); label every unverified statement; make the first action with credentials a single end-to-end run of §6 step 1. | `[BLOCKED — NO BIGQUERY ACCESS]` |
| DQ-02 | **Date coverage is assumed, not measured.** The exploration queries filter `_TABLE_SUFFIX BETWEEN '20201101' AND '20201103'` — a 3-day slice of a documented 2020-11-01…2021-01-31 range (≤92 daily shards). Whether every shard in a wider window exists, and whether any day is absent, is unknown. | Window literals in `sql/exploration/00`–`07` (the full range is documented as an alternative in `00` and `sql/exploration/README.md`); documented coverage in `docs/dataset_research.md`. Detection logic: `check_date_coverage` + `tests/test_quality_checks.py::TestCheckDateCoverage::test_missing_day_is_detected` (SYNTHETIC input). | A missing shard silently deletes a day instead of showing zero: trends, week-over-week and rolling averages break, and a chart looks complete while being wrong. A 3-day window labelled "monthly" answers a different question than the one presented. | **High** | Run the calendar-spine query in §6 and feed the result to `check_date_coverage`; print the window in every chart title; never label a 3-day window as monthly. | Detection `[VERIFIED — local test]`; dataset coverage `[BLOCKED — NO BIGQUERY ACCESS]` |
| DQ-03 | **Schema consistency across shards is assumed.** Wildcard reads (`events_*`) fail if a shard has a different schema (GA4 adds fields over time). All current queries read wildcards. | Static guard `tests/test_sql_queries.py::test_events_wildcard_requires_table_suffix_filter` proves every wildcard read is date-filtered; schema equality itself has not been checked. | A column missing from one shard makes the query fail (loud, recoverable) *or* silently drops rows/fields in that shard (quiet, corrupting a partial window's revenue or items). | **Medium** — impact would be High if confirmed, but there is no evidence of drift inside a 3-month window and the check is one cheap query | Compare the column set per shard (§6); keep every read `_TABLE_SUFFIX`-filtered so the blast radius is one day, not the dataset. | `[BLOCKED — NO BIGQUERY ACCESS]` (guard: `[VERIFIED — local test]`) |

**B. Identifier completeness**

| ID | Finding | Evidence | Impact on downstream metric/product | Severity | Mitigation | Verification status |
|---|---|---|---|---|---|---|
| DQ-04 | **Missing pseudonymous user ids are expected GA4 behaviour, not corruption.** `user_pseudo_id` is derived from a client-side identifier, so users who decline consent, block cookies or arrive in a context where the identifier cannot be written produce rows without a usable user id. The real rate is unknown. | GA4 semantics documented in `docs/data_dictionary.md`/`docs/dataset_research.md`; measurement logic `check_no_null_identifiers` + tests `test_missing_id_is_reported_as_rate`, `test_message_separates_expectation_from_corruption`, `test_whitespace_only_id_counts_as_missing`. | Those sessions still exist and still count for session-level metrics, but they cannot be attributed to a user. User-level funnels and retention lose rows: an unreported exclusion silently shrinks the funnel top and inflates every user-based rate. | **Medium** | Exclude them **and report the excluded share** next to the metric; compute funnels at session grain where user grain is impossible; the check returns the rate so the denominator can be adjusted transparently. | Semantics `[DOCUMENTED]`; detection `[VERIFIED — local test]`; rate `[BLOCKED — NO BIGQUERY ACCESS]` |
| DQ-05 | **Missing session identifiers behave the same way** and are equally unmeasured: `ga_session_id` is absent when an event cannot be attached to a session, which removes rows from every session-level denominator. | `check_no_null_identifiers` (documented for `user_pseudo_id`, applied to `ga_session_id` in `sql/exploration/03_user_identification.sql`); tests as in DQ-04. | Session counts and session-based conversion rates are computed over an unknown subset; "sessions" and "rows" silently stop matching. | **Medium** | Measure the rate per query, exclude missing-id rows explicitly, and state the measured population in the metric definition. | Semantics `[DOCUMENTED]`; detection `[VERIFIED — local test]`; rate `[BLOCKED — NO BIGQUERY ACCESS]` |
| DQ-06 | **`ga_session_id` alone is not a global key.** It is a timestamp-derived integer written per session *with* `user_pseudo_id`, so two users can hold the same value; only `(user_pseudo_id, ga_session_id)` identifies a session. Reuse frequency in the sample is unknown. | GA4 semantics documented in `docs/dataset_research.md`; measurement logic `check_session_id_reuse` + tests `test_reuse_is_observed_and_matches_expectation`, `test_pipeline_assuming_global_uniqueness_is_alarmed` (the check fails loudly when a caller assumes global uniqueness). Committed proof query: `sql/exploration/07_session_feasibility.sql` (queries 1–3: availability, composite-key proof, raw collisions). | Any join, de-duplication or session count keyed on `ga_session_id` alone merges unrelated sessions: inflated session counts, "a session with two entry pages", corrupted entry-channel attribution — all invisible in the output. | **High** (silently wrong, hard to notice) | Enforce the composite key in every query and in the semantic layer; run `check_session_id_reuse` on any session aggregate before it feeds a metric. | Semantics `[DOCUMENTED]`; detection `[VERIFIED — local test]`; real reuse rate `[BLOCKED — NO BIGQUERY ACCESS]` |

**C. Event and purchase integrity**

| ID | Finding | Evidence | Impact on downstream metric/product | Severity | Mitigation | Verification status |
|---|---|---|---|---|---|---|
| DQ-07 | **A purchase can appear on several rows with the same `transaction_id`, each repeating its revenue.** Retries, reloads, resumed payments and multi-session checkout flows all re-fire `purchase`. The duplication rate in the sample is unknown. | `check_purchase_transaction_duplicates` + tests `test_duplicate_transaction_is_flagged`, `test_null_and_empty_ids_are_not_duplicate_groups`, `test_placeholder_ids_are_treated_as_missing` (SYNTHETIC: one id duplicated, one NULL and one empty id). Committed measurement query: `sql/exploration/06_purchase_revenue_audit.sql` (query 5). | Revenue, order count, AOV and any revenue-derived ratio (conversion value, campaign value) are inflated by an unknown factor; the error is undetectable by looking at the total, which is exactly why it survives review. | **High** | De-duplicate by `transaction_id` (one row per order, e.g. latest `event_timestamp`) before summing revenue; count orders with `COUNT(DISTINCT transaction_id)`; publish the duplicate rate as a QC metric. | Detection `[VERIFIED — local test]`; dataset rate `[BLOCKED — NO BIGQUERY ACCESS]` |
| DQ-08 | **Revenue fields are only populated on purchase rows, and `purchase_revenue` is currency-bound.** `purchase_revenue` is expressed in the event/property currency; `purchase_revenue_in_usd` is the normalised counterpart. On every non-purchase event both are NULL — i.e. NULL is the *normal* state of most rows. Real null rates per field are unknown. | `check_revenue_null_rate` + tests `test_partial_nulls_are_reported_with_ga4_explanation`, `test_fully_null_column_is_high_severity`; documentation in `docs/data_dictionary.md`; committed measurement query `sql/exploration/06_purchase_revenue_audit.sql` (query 2). | An average computed over all rows (including non-purchase rows) reports a near-zero order value; a NULL rate that is not measured hides which field a metric actually used; summing raw `purchase_revenue` across currencies compares incomparable amounts. | **Medium** | Compute revenue metrics **on the purchase-event grain only**; prefer `purchase_revenue_in_usd` for any cross-currency or multi-store aggregate; name the field used on every metric card; run the null-rate check on the aggregate. | Semantics `[DOCUMENTED]`; detection `[VERIFIED — local test]`; rates `[BLOCKED — NO BIGQUERY ACCESS]` |
| DQ-09 | **Repeated events are normal; duplicated aggregate rows are not.** GA4 has no primary key: one session emits many events, and two visually identical events can both be legitimate. The defect appears one level up — when an aggregate contains the same key twice. The real duplication rate is unknown. | `check_duplicate_composite_key` + tests `test_duplicate_session_rows_are_flagged`, `test_incomplete_keys_are_excluded_and_counted`, `test_single_column_key_is_supported`; message explains the repeat-vs-duplicate distinction. | Counting rows in a session-level aggregate that has lost its grain over-counts sessions, which inflates the top of the funnel (and therefore understates every conversion rate below it). | **Medium** (the defect is loud once the grain is checked; the risk is that nobody checks) | Always state the grain of a query (`GROUP BY` key = the metric's unit); run the composite-key check on every new aggregate; keep event counts and session counts in different columns so the units cannot be confused. | Semantics `[DOCUMENTED]`; detection `[VERIFIED — local test]`; dataset rate `[BLOCKED — NO BIGQUERY ACCESS]` |
| DQ-10 | **Event presence for the modelled funnel is unverified.** GrowthScope models 13 events (`view_item`, `add_to_cart`, `begin_checkout`, `add_payment_info`, `purchase`, …). A step whose event is absent or rare is not "0 % conversion" — it is "not observed in this window". | `sql/exploration/05_funnel_event_audit.sql` (presence audit per event and per date, including zero rows) and `sql/exploration/01_event_inventory.sql`; `check_funnel_monotonicity` + tests `test_growing_step_is_flagged`, `test_null_step_is_reported_as_unverifiable` verify the funnel-shaped object. | A missing step silently produces a 0 % conversion rate and a wrong growth recommendation ("users abandon before checkout"), which is the most damaging class of error for a growth product because it *looks* like a finding. | **High** | Gate the funnel on the presence audit; render unobserved steps as "not observed in window", never as 0 %; keep zero-fill sparse (a real zero and a missing day are different facts). | Query written `[DOCUMENTED]` (`sql/exploration/05`); presence result `[BLOCKED — NO BIGQUERY ACCESS]`; funnel invariant `[VERIFIED — local test]` |
| DQ-11 | **Item-grain join fan-out can multiply revenue.** Purchased line items live in the repeated `items` array on the same purchase event: `item_revenue` is per item, `purchase_revenue` is per transaction. Joining both at one grain multiplies revenue by basket size. The real basket-size distribution is unknown. | Semantics documented in `docs/data_dictionary.md` (REPEATED `items`); `check_purchase_transaction_duplicates` + `check_duplicate_composite_key` verify the detection machinery that catches the resulting duplicate keys; `sql/exploration/06_purchase_revenue_audit.sql` (query 4) measures item-level availability and the event-vs-item grain comparison. | `SUM(purchase_revenue)` over item-grain rows inflates revenue (and order counts) by the average basket size — a plausible-looking overstatement by a factor of ~2–3 that passes every eyeball test. | **High** | One grain per query: unnest `items` only in item-grain queries, and never mix event-grain and item-grain measures in the same `SELECT`; reconcile `SUM(item_revenue)` against `SUM(purchase_revenue)` as a QC step. | Semantics `[DOCUMENTED]`; detection `[VERIFIED — local test]`; real reconciliation `[BLOCKED — NO BIGQUERY ACCESS]` |

**D. Semantics that change a number's meaning**

| ID | Finding | Evidence | Impact on downstream metric/product | Severity | Mitigation | Verification status |
|---|---|---|---|---|---|---|
| DQ-12 | **`event_timestamp` is in microseconds (UTC), not seconds or milliseconds.** A unit mix-up places events near 1970 (milliseconds read as micros) or near the year 56000 (micros read as seconds), and breaks partition pruning. | `micros_to_datetime` + `check_timestamp_validity`; tests `test_converts_microseconds_to_utc` (asserts `1_610_000_000_000_000` → `2021-01-07T06:13:20Z`), `test_implausible_and_null_timestamps_are_flagged`, `test_datetime_column_is_supported`. | Every time-series metric (daily volume, funnel timing, retention windows, cohort dates) is wrong, often without erroring: the numbers still look like numbers. | **Medium** — impact is High, but the risk is centralised in one tested helper and a window check rather than left to each query | Convert only through `micros_to_datetime`, filter shards on `_TABLE_SUFFIX`, and run `check_timestamp_validity` with explicit window bounds on every timestamp column that reaches a metric. | `[VERIFIED — local test]` (code path); actual min/max window `[BLOCKED — NO BIGQUERY ACCESS]` |
| DQ-13 | **Several currencies can coexist in one revenue aggregate.** GA4 stores the event currency per row; summing the raw revenue field across currencies adds non-comparable amounts while the column carries no unit. The number of distinct currencies in the sample is unknown. | `check_currency_consistency` + tests `test_multiple_currencies_are_flagged`, `test_currency_codes_are_normalised`, `test_placeholders_are_not_counted_as_a_currency`; documented dual revenue fields in `docs/data_dictionary.md`; committed enumeration query `sql/exploration/06_purchase_revenue_audit.sql` (query 3). | Revenue totals, AOV and channel value become meaningless (100 JPY counted as 100 USD) with no visible symptom; rankings between channels can invert. | **Medium** — would be High if a mixed-currency sum were ever published | Aggregate the USD-normalised field for anything cross-currency, or filter to one currency and state it in the metric definition; run the currency check on every revenue aggregate. | Semantics `[DOCUMENTED]`; detection `[VERIFIED — local test]`; real distribution `[BLOCKED — NO BIGQUERY ACCESS]` |
| DQ-14 | **GA4 writes placeholder strings instead of NULLs.** `(not set)` (and similar) appear in dimension fields, and reporting surfaces can group high-cardinality values into `<Other>`. A placeholder is a legitimate "unknown" category, not a real source/page/campaign. | Placeholder handling implemented in `check_purchase_transaction_duplicates` and `check_currency_consistency`; tests `test_placeholder_ids_are_treated_as_missing`, `test_placeholders_are_not_counted_as_a_currency`. | Treating `(not set)` as an ordinary value creates a fake top channel/page and hides the true unknown share; conversely, silently dropping it changes denominators without telling the user. | **Low** | Classify placeholders as an explicit `unknown` category in the semantic layer and always display the unknown share instead of dropping it. | Semantics `[DOCUMENTED]`; handling `[VERIFIED — local test]`; real share `[BLOCKED — NO BIGQUERY ACCESS]` |
| DQ-15 | **Attribution is first-user-biased.** The export's `traffic_source` is *first-user* acquisition, while session-scope source lives elsewhere; a returning user keeps their original channel. Mixing the two produces channel numbers that cannot be reconciled. | Schema/field semantics documented in `docs/dataset_research.md` and `docs/data_dictionary.md`; the metric dictionary's channel definitions rely on this distinction. | "Which channel drives purchases in this window" is systematically biased toward acquisition channels; a recommendation to shift budget would be made on a metric that answers a different question. | **Medium** | State the attribution model on every channel metric; use session-scoped source for in-window performance and first-user source only for acquisition/cohort analysis; never plot the two in one series. | `[DOCUMENTED]`; per-channel distribution `[BLOCKED — NO BIGQUERY ACCESS]` |
| DQ-16 | **`event_date` (property timezone) and `event_timestamp` (UTC) do not agree on day boundaries.** Events late in the local day fall on the next UTC day, so a day-grouped series built from truncated UTC timestamps shifts traffic between days. | Documented GA4 timezone semantics (property reporting timezone) in `docs/dataset_research.md`; `check_timestamp_validity` documents the UTC basis of the microsecond column; `sql/exploration/07_session_feasibility.sql` (query 6) measures midnight-crossing sessions; the day-attribution gap itself has not been measured. | Daily and weekly comparisons shift by a few hours of traffic: a "Tuesday spike" can be a timezone artefact, and two dashboards that group differently disagree permanently. | **Medium** | Group days by `event_date` for reporting, filter months with `_TABLE_SUFFIX`, and never mix an `event_date` series with a UTC-truncated timestamp series in one chart or ratio. | `[DOCUMENTED]`; mismatch count `[BLOCKED — NO BIGQUERY ACCESS]` |
| DQ-17 | **The dataset is a Google-obfuscated sample of one property, in a fixed 3-month window, with no cost data.** It contains no ad spend, no margin, no fulfilment or cancellation cost, and refund coverage is unverified. | `docs/dataset_research.md` documents provenance (obfuscation, fixed window) and the absence of cost fields; no query in `sql/exploration/` reads a cost column because none exists. | CAC, ROAS, profit and incrementality are **not computable**. Publishing any efficiency metric would be fabrication — the single most damaging thing a growth product can do to its own credibility. Absolute revenue figures are a modelled sample, not a business result; only *methods and relative behaviour* generalise. | **Informational** as a data property; **High** if presented as a real business without disclosure | Label every screen with source + window ("Google obfuscated sample, Nov 2020 – Jan 2021"); restrict the product to behavioural metrics (funnel, retention, channel mix, conversion); treat any future efficiency metric as user-supplied input, labelled as such. | `[DOCUMENTED]`; live re-confirmation `[BLOCKED — NO BIGQUERY ACCESS]` |
| DQ-18 | **Volume, sampling and cardinality bonuses/limits are unknown**: total events per day, distinct users, distinct items, session depth. Without them the cost of a query and the statistical weight of a finding cannot be judged. | `sql/exploration/02_daily_event_volume.sql` is written to measure exactly this (and documents that summing daily distinct users double-counts returning users across days); no result exists yet. | A demo built on a 3-day slice may present a handful of sessions as a trend; a "top channel" claim may rest on a dozen users. Cheap to measure, expensive to guess. | **Medium** | Run the daily-volume query first, state the measured population on every finding, and suppress or mark as "below threshold" any slice with too few users/orders to be meaningful. | Query written `[DOCUMENTED]` (`sql/exploration/02`); result `[BLOCKED — NO BIGQUERY ACCESS]` |

### 4.1 Findings that are NOT data corruption

GrowthScope publishes growth advice; a defect wrongly labelled "data corruption" is
as damaging as a real one, because it can trigger unnecessary exclusions, or train
the team to ignore the finding. These are **analytical limitations or documented
behaviours**, deliberately separated from defects:

1. **Missing pseudonymous user ids (DQ-04) and session ids (DQ-05)** — caused by
   consent choices and client-side restrictions. The sessions are real and countable;
   only *user-level attribution* is impossible. Handling: exclude and report the
   excluded share. This must never be rendered as an error state.
2. **Repeated events inside one session (DQ-09)** — one row per event is GA4's
   design; several events per session is the normal case. Only a repeated *key in an
   aggregate* is a defect.
3. **NULL revenue on non-purchase rows (DQ-08)** — the normal state of the vast
   majority of rows, not an incompleteness of the data. A revenue metric that counts
   those rows is wrong; the data is not.
4. **Multiple currencies (DQ-13)** — a property can legitimately sell in several
   currencies. The limitation belongs to the *aggregation*, not the export.
5. **`(not set)` / `<Other>` placeholders (DQ-14)** — GA4's representation of
   "unknown", produced by privacy filters and cardinality limits. A category to
   expose, not a row to delete.
6. **First-user attribution (DQ-15)** — a definition choice by GA4, not an error.
   The defect would be *unlabelled mixing* of attribution models.
7. **`ga_session_id` reuse across users (DQ-06)** — a direct consequence of a
   per-user session counter. The data is correct; the naive key is wrong.
8. **Fixed window, obfuscation and absence of cost data (DQ-17)** — properties of a
   public sample dataset. Scope boundaries, not defects; they become dishonest
   findings only if undisclosed.
9. **Query cost and scan volume** — not a data-quality issue at all. It is handled
   as a static guard in `tests/test_sql_queries.py` (`_TABLE_SUFFIX` required on
   every wildcard read, no bare `SELECT *`).

---

## 5. What the check library guarantees (and what it does not)

| Check | Guards against | Status |
|---|---|---|
| `check_no_null_identifiers` | unreported loss of user-level attribution | `[VERIFIED — local test]` |
| `check_duplicate_composite_key` | a session aggregate that lost its grain (fan-out join, missing `GROUP BY` key) | `[VERIFIED — local test]` |
| `check_purchase_transaction_duplicates` | double-counted orders and revenue (`transaction_id` repeats) | `[VERIFIED — local test]` |
| `check_funnel_monotonicity` | a non-nested funnel producing > 100 % conversion rates | `[VERIFIED — local test]` |
| `check_date_coverage` | a missing export shard disguised as a zero day | `[VERIFIED — local test]` |
| `check_timestamp_validity` / `micros_to_datetime` | the microsecond unit trap (seconds/ms/micros confusion), NULL timestamps | `[VERIFIED — local test]` |
| `check_currency_consistency` | summing incomparable currency amounts | `[VERIFIED — local test]` |
| `check_revenue_null_rate` | a revenue field silently treated as 0, or averaged over the wrong grain | `[VERIFIED — local test]` |
| `check_session_id_reuse` | joins keyed on `ga_session_id` alone; an explicit uniqueness assumption that is false | `[VERIFIED — local test]` |
| `check_share_bounds` | a rate outside `[0, 1]` from mismatched numerator/denominator grains | `[VERIFIED — local test]` |

What the library does **not** do: it does not validate the raw export, it cannot tell
whether an aggregate answers the *right* question, and it cannot upgrade any
`[BLOCKED]` finding above into a verified one.

---

## 6. What would change if BigQuery access were available

One credential turns most of §4 from "unknown" into "measured". The work is already
written down; this is the exact order to run it in. Queries marked *committed* live in
`sql/exploration/` today.

**Step 1 — run the committed queries and record raw output** (nothing in this
document may be upgraded until the output is stored). `sql/exploration/README.md`
holds the authoritative execution order; the 8 files map to findings as follows:

1. `sql/exploration/00_project_settings.sql` — preflight: which shards exist in the window (**DQ-02**, **DQ-01**), settings and cost notes.
2. `sql/exploration/01_event_inventory.sql` — closes the event-taxonomy half of **DQ-10**.
3. `sql/exploration/02_daily_event_volume.sql` — closes **DQ-18** and gives every later finding a denominator.
4. `sql/exploration/03_user_identification.sql` — closes the rates for **DQ-04**, **DQ-05**.
5. `sql/exploration/04_event_parameters.sql` — confirms which parameters exist (and documents `traffic_source` vs `collected_traffic_source`, **DQ-15**) before any metric depends on them.
6. `sql/exploration/05_funnel_event_audit.sql` — closes the presence half of **DQ-10** (per-event and per-date presence, zeros included).
7. `sql/exploration/06_purchase_revenue_audit.sql` — closes **DQ-07** (transaction identity, duplicate `transaction_id`), **DQ-08** (which revenue field is populated), **DQ-13** (currency values) and **DQ-11** (item-level availability and reconciliation); its query for transaction identity also returns the `TIMESTAMP_MICROS` first/last-seen bounds needed by **DQ-12**.
8. `sql/exploration/07_session_feasibility.sql` — closes **DQ-06** (composite-key proof, `ga_session_id` collisions) and measures session depth and midnight-crossing sessions, which is the local counterpart of **DQ-16**.

**Step 2 — the verification queries still missing** (proposed here, not yet committed;
each one feeds a check from §5 directly):

* **DQ-02 — date coverage.** Compare a calendar spine against the shards that exist
  (`00` lists the shards; this query names the *missing* days explicitly, which is
  what `check_date_coverage` consumes):
  ```sql
  WITH present AS (
    SELECT PARSE_DATE('%Y%m%d', _TABLE_SUFFIX) AS day, COUNT(*) AS rows_seen
    FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
    GROUP BY day
  )
  SELECT spine.day
  FROM UNNEST(GENERATE_DATE_ARRAY(DATE '2020-11-01', DATE '2021-01-31')) AS spine(day)
  LEFT JOIN present USING (day)
  WHERE present.day IS NULL
  ORDER BY spine.day;
  ```
  Expected window = the documented range; feed the result to `check_date_coverage`.
* **DQ-01 / DQ-03 — schema equality across shards.** `INFORMATION_SCHEMA.COLUMNS`
  for the dataset, compared per shard (`00` deliberately avoids `INFORMATION_SCHEMA`,
  because its availability varies by dataset, so this must be attempted separately).
* **DQ-16 — timezone boundary.** Count rows where
  `PARSE_DATE('%Y%m%d', event_date) != DATE(TIMESTAMP_MICROS(event_timestamp))`, plus
  the hourly distribution of that difference. `07` measures midnight-crossing
  sessions from the event side; this query measures the day-attribution gap itself.
* **DQ-14 — placeholder volume.** Counts of `(not set)` / `<Other>` literals per
  dimension field that a metric groups by (channel, page, item).
* **QC wiring.** Feed each stored result to the matching check in
  `src/growthscope/quality/checks.py` and publish the `CheckResult` evidence
  (`to_dict()` is JSON-ready) next to the metric it qualifies.

**Step 3 — calibrate and re-audit.** Set each check's tolerance from the measured
distribution (strict `0.0` defaults are placeholders, not policy), promote every
`[BLOCKED]` row to `[VERIFIED — query <file>, <date>]`, and only then let any metric
carry a "verified" badge in the product.

**Until then:** no metric on screen, in the README, or in a demo may be presented as
computed from the dataset. The demo path must be labelled as replay or synthetic
(`tests/fixtures/README.md` sets the same rule for test data).

---

## 7. Re-running this audit

```bash
# From the repository root, with the virtualenv already created:
.\.venv\Scripts\python.exe -m pytest tests -v          # 122 passed, 1 skipped (quality + static SQL)
.\.venv\Scripts\python.exe -m pytest tests/test_sql_queries.py -v   # static contract checks on sql/exploration/*.sql
.\.venv\Scripts\python.exe -m pytest tests/test_quality_checks.py -v
```

The suite skips cleanly (never fails) when `sql/exploration/` or a real fixture CSV
is absent, so it is safe on a clean checkout and in CI.

## Appendix A — Test-to-finding map

Counts are the collected test cases per class (parametrised cases counted individually): 116 in
`tests/test_quality_checks.py`, 7 in `tests/test_sql_queries.py`, 123 total.

| Finding | Verifying tests (`tests/test_quality_checks.py`) |
|---|---|
| DQ-02 | `TestCheckDateCoverage` (13: gap, out-of-range day, empty frame, duplicate days, date objects, numeric date column, reversed/unparsable/NULL window, mixed offsets, error contract) |
| DQ-04, DQ-05 | `TestCheckNoNullIdentifiers` (12: rate, empty/whitespace id as missing, tolerance, empty frame, error contract) |
| DQ-06 | `TestCheckSessionIdReuse` (10: reuse observed, uniqueness assumption violated, both pass directions, nullable ids, excluded rows) |
| DQ-07 | `TestCheckPurchaseTransactionDuplicates` (11: duplicated id, NULL/empty ids, placeholders, numeric ids, all-missing frame) |
| DQ-08 | `TestCheckRevenueNullRate` (10: partial and total NULL, tolerance, sums as evidence, non-numeric column) |
| DQ-09, DQ-11 | `TestCheckDuplicateCompositeKey` (11: duplicated key, single-column key, incomplete keys, bare-string/set arguments) |
| DQ-10 | `TestCheckFunnelMonotonicity` (11: monotonic, growing step, per-row counting, equal steps, NULL step, non-numeric column) |
| DQ-12 | `TestMicrosToDatetime` (5: µs→UTC, NaT, datetime input, dtype errors) + `TestCheckTimestampValidity` (10: in-window, below/above/NULL rows, datetime column, bound errors) |
| DQ-13 | `TestCheckCurrencyConsistency` (8: single currency, normalisation, multiple currencies, placeholders, no usable value) |
| denominator/grain hygiene (DQ-09, DQ-18) | `TestCheckShareBounds` (9: in-range, impossible rates, custom bounds, NULLs, bound errors) + `TestCheckResultModel` (4: severity scale, frozen result, JSON-serialisable payload) |
| DQ-01 (static guard) | `tests/test_sql_queries.py` (7: `Purpose`+`Caveats` headers, read-only, wildcard + `_TABLE_SUFFIX`, no bare `SELECT *`, non-empty, path sanity) |
| fixture policy | `TestChecksOnMultipleAggregates` (2: one result per check is JSON-serialisable; human-added CSVs load, or the test skips) |

Findings **DQ-03, DQ-14, DQ-15, DQ-16 and DQ-17** deliberately have no local test:
they are statements about GA4's documented behaviour or about the dataset itself, and
their status is `[DOCUMENTED]` / `[BLOCKED — NO BIGQUERY ACCESS]`. Writing a test that
"passes" on a synthetic frame would create the impression of a verified finding, which
is exactly what this audit is meant to prevent.

