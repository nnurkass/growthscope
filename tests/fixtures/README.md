# Test fixtures — policy

## The rule

**Only synthetic fixtures are committed to this repository.**

A fixture in this folder is data. Data in a public repository is permanent, is
indexed by search engines, and cannot be un-published if it turns out to contain
something it should not. The rules for this project are therefore:

1. **No raw user-level data, ever.** No GA4 event rows, no session rows with
   `user_pseudo_id`, no `transaction_id` values from a real store, no exported
   CSV from a real property. Not even one row. Not even "obfuscated". The GA4
   sample dataset is Google-obfuscated, but the samples it is *modelled on* are
   real e-commerce properties, and a habit of committing raw exports is how PII
   leaks.
2. **Hand-written fixtures live in code, not here.** The frames used by the test
   suite are built in `tests/conftest.py` and named with a `syn_` prefix. They
   contain invented identifiers (`u1`, `1001`, `T-1001`) and are documented in
   their own docstrings, so a reader can see immediately that a number in a test
   assertion is not a fact about the dataset.
3. **No fixture may be reused as a result.** Synthetic frames exist to exercise
   code paths (a duplicated key, a gap, a NULL). They must never be quoted in
   `docs/data_quality_audit.md` or any other document as evidence about real
   data. Findings about the real dataset are either verified in BigQuery or
   marked `[BLOCKED — NO BIGQUERY ACCESS]`.
4. **Fixtures must not be labelled real.** A synthetic frame that mimics the
   shape of a real aggregate is fine; presenting it as a live result (for example
   as a screenshot in the demo) is not. If a demo needs a labelled placeholder,
   the UI must say `SYNTHETIC / DEMO DATA`.

## Adding a real aggregate fixture (optional, for advanced readers)

If you want to check `growthscope.quality` against your own data, you may add a
CSV **that you have already aggregated yourself** to this directory. It is not
committed by default (`.gitignore`/review), and it must satisfy every condition
below:

* **Aggregated, not raw.** One row per day, per session, per step or per
  transaction — never one row per event. The checks are written for aggregates;
  raw event exports are out of scope by design (and would be too large to
  review).
* **No direct identifiers.** No names, emails, addresses, phone numbers, IP
  addresses, `user_pseudo_id` values, or `transaction_id` values that could be
  matched back to an order. Prefer counts, shares and averages.
* **Small.** A few dozen rows are enough for any check in this library. If you
  need volume, generate it synthetically instead.
* **Column names match GA4/documentation.** Use the real field names
  (`event_date`, `ga_session_id`, `purchase_revenue`, `purchase_revenue_in_usd`)
  so the fixtures stay readable next to `sql/exploration/`. Document any
  deviation in the CSV's own README line.
* **Clearly named.** Something like `my_property_daily_aggregate.csv`, never
  `events.csv` or `data.csv`.
* **Documented.** Add one line here describing the file, its grain, its columns
  and its date range.

`pytest` picks the files up automatically through the session-scoped
`real_aggregate_fixtures` fixture in `tests/conftest.py`; the test that uses it
skips when this directory contains no CSV, so a clean checkout stays green.

## Why this is not over-cautious

GrowthScope is a portfolio project published on GitHub. A quality auditor who
commits raw customer data while claiming to care about data quality has failed
the interview question they were trying to answer. The synthetic-fixtures rule is
part of the deliverable, not paperwork around it.
