# `data/sample/` — aggregate result sets only

This directory holds **small, pre-computed aggregate result sets** produced by the exploration
SQL in `sql/exploration/`. They exist so that the analysis can be inspected and the notebook can
be run without a Google Cloud account.

## Hard rules

| Rule | Reason |
|---|---|
| **Only aggregated results.** No row-level event data, ever. | The source data describes real (if obfuscated) user behaviour. Publishing row-level extracts would be an unnecessary privacy exposure and would bloat the repository. |
| **Only aggregates small enough to read.** Target: under a few hundred KB per file. | A committed file must be reviewable, not a data dump. |
| **Every file must be traceable.** Record the query file, the exact `_TABLE_SUFFIX` window and the execution date. | An aggregate without a window and query reference is not reproducible and therefore not citable. |
| **Never commit credentials or query logs.** | Standard secret hygiene; see `.gitignore`. |

## Naming convention

The notebook resolves files in `sample` mode by matching the SQL file stem:

```text
sql/exploration/01_event_inventory.sql          ->  data/sample/01_event_inventory.csv
sql/exploration/02_daily_event_volume.sql       ->  data/sample/02_daily_event_volume.csv
sql/exploration/03_user_identification.sql      ->  data/sample/03_user_identification.csv
sql/exploration/04_event_parameters.sql         ->  data/sample/04_event_parameters.csv
sql/exploration/05_funnel_event_audit.sql       ->  data/sample/05_funnel_event_audit.csv
sql/exploration/06_purchase_revenue_audit.sql   ->  data/sample/06_purchase_revenue_audit.csv
sql/exploration/07_session_feasibility.sql      ->  data/sample/07_session_feasibility.csv
```

## How to populate this directory

Run the notebook in `live` mode with the export flag enabled:

```bash
export GROWTHSCOPE_EXPORT_SAMPLE=1     # Windows: $env:GROWTHSCOPE_EXPORT_SAMPLE="1"
export GROWTHSCOPE_NOTEBOOK_MODE=live
jupyter lab notebooks/01_data_discovery.ipynb
```

The final notebook cell writes one CSV per analysis section into this directory. Then add a row to
the provenance table below and commit.

## Provenance table

**Currently empty.** No aggregate result set has been produced, because no BigQuery credentials
were available in the build environment. This is recorded honestly rather than filled with
invented numbers — see `docs/data_quality_audit.md`.

| File | Query | `_TABLE_SUFFIX` window | Executed (UTC) | Bytes scanned | Executed by |
|---|---|---|---|---|---|
| *(none yet)* | — | — | — | — | — |

## A note on `data/raw/` and `data/tmp/`

Both are git-ignored. `data/raw/` is for local-only exports; `data/tmp/` for scratch files.
Neither is expected to exist in a fresh clone.
