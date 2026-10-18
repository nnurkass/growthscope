# Sprint 01 Delivery Report — Project Foundation & Data Discovery

**Sprint:** 01 — Project Foundation & Data Discovery
**Repository:** <https://github.com/nnurkass/growthscope>
**Branch:** `main`
**Status:** **PARTIAL — foundation and analysis layer delivered and locally verified; live dataset execution blocked by the absence of Google Cloud credentials in the build environment.**

---

## 1. Executive summary

Sprint 01 established a working, tested and documented foundation for GrowthScope: a reproducible Python environment, eight cost-guarded BigQuery exploration queries, a ten-check data-quality library with a 122-test suite, an executable ten-section analysis notebook, and six technical documents including two dictionaries and a severity-classified data-quality audit.

The single unmet objective is **live execution against BigQuery**. The build environment had no `gcloud`, no `bq`, no Application Default Credentials and no authenticated `gh`; the BigQuery REST endpoint returned **HTTP 401**. Rather than substitute plausible-looking numbers, every statistic that requires the dataset is marked `[BLOCKED — NO BIGQUERY ACCESS]` and left empty, with the exact query that will produce it named alongside.

What this sprint therefore delivers is a **complete, runnable analysis pipeline with an honest, explicit gap** — plus the cost and correctness guardrails that make the first live run cheap and safe.

---

## 2. Environment as found

| Item | Observed |
|---|---|
| OS | Windows (`win32`) |
| Python | 3.12.10 (system installation) |
| Virtual environment | `.venv`, created and populated during the sprint |
| Git | 2.55.0.windows.5; repository already initialised, remote `origin` = `nnurkass/growthscope` |
| Pre-existing work | `README.md`, `LICENSE` (MIT), `.gitignore`, one commit (`7e9a788`) — **preserved, not overwritten** |
| GitHub CLI (`gh`) | **not installed**; `git` remote access worked through cached Credential Manager credentials |
| `gcloud` / `bq` | **not installed** |
| Google credentials | none found (no ADC file in `%APPDATA%\gcloud` or `~/.config/gcloud`, no service-account keys) |
| Network | reachable; `https://bigquery.googleapis.com/bigquery/v2/projects` → **HTTP 401** |
| Python packages | none installed at start; installed into `.venv` during the sprint |

Pre-existing `README.md`, `LICENSE` and `.gitignore` were treated as the owner's work: the README was **extended**, not replaced, and its vision, module table, funnel concept and roadmap were preserved.

---

## 3. Work division

Five specialised subagents were launched as **real native subagents** (separate agent sessions with independent context), not simulated as sections of one response. File ownership was assigned before launch so that no two agents wrote the same file.

| Agent | Role | Owned files |
|---|---|---|
| Orchestrator | Architecture, contracts, integration, verification, git | `docs/sprint_01_report.md`, `notebooks/01_data_discovery.ipynb`, `data/sample/README.md`, `.env.example` additions |
| **A** | Data Source Researcher | `docs/dataset_research.md` |
| **B** | SQL & Data Exploration Engineer | `sql/exploration/00..07_*.sql`, `sql/exploration/README.md` |
| **C** | Data Quality & Testing Engineer | `src/growthscope/quality/**`, `tests/**`, `docs/data_quality_audit.md` |
| **D** | Repository & Documentation Engineer | `README.md`, `requirements.txt`, `pyproject.toml`, `.env.example`, `docs/architecture.md`, `docs/data_dictionary.md`, `docs/metric_dictionary.md` |
| **E** | Independent Reviewer (adversarial) | none — read-only by design |

Agents A, B, C and D ran **concurrently** on disjoint file sets. Agent E ran afterwards as an independent reviewer, because the orchestrator must not accept producers' self-reports as verification.

---

## 4. Deliverables

| # | Deliverable | Path | Status |
|---|---|---|---|
| 1 | Repository structure | repository root | Done |
| 2 | Python environment | `.venv` + `requirements.txt` + `pyproject.toml` | Done |
| 3 | Environment template | `.env.example` | Done |
| 4 | BigQuery exploration queries | `sql/exploration/00..07_*.sql` (8 files, read-only) | Done — structurally verified, runtime blocked |
| 5 | Query execution guide | `sql/exploration/README.md` | Done |
| 6 | Exploratory notebook | `notebooks/01_data_discovery.ipynb` (44 cells, 10 sections) | Done — executes in 4 modes |
| 7 | Data-quality library | `src/growthscope/quality/` (10 checks + 1 converter) | Done — unit-tested |
| 8 | Test suite | `tests/` (123 collected) | Done — 122 pass, 1 skip by design |
| 9 | Data-quality audit | `docs/data_quality_audit.md` (18 findings) | Done — code findings verified, dataset findings blocked |
| 10 | Dataset research | `docs/dataset_research.md` | Done — from official documentation |
| 11 | Data dictionary | `docs/data_dictionary.md` | Done — structure documented, live fields marked unverified |
| 12 | Metric dictionary | `docs/metric_dictionary.md` | Done — 20+ metrics, all `PROPOSED` / `BLOCKED` |
| 13 | Architecture document | `docs/architecture.md` | Done |
| 14 | Sample-data policy | `data/sample/README.md` | Done — provenance table currently empty, on purpose |
| 15 | Delivery report | `docs/sprint_01_report.md` | This document |

---

## 5. Verified findings

Verification status is stated per item. **No number in this section was produced by a query against the public dataset.**

### 5.1 Documentation-verified (`[DOCUMENTED]`)

| Finding | Source |
|---|---|
| Dataset reference `bigquery-public-data.ga4_obfuscated_sample_ecommerce`, table pattern `events_YYYYMMDD` | <https://developers.google.com/analytics/bigquery/web-ecommerce-demo-dataset> |
| Coverage 2020-11-01 → 2021-01-31 (≈92 daily shards) | same |
| GA4 export schema: top-level columns, nested `event_params`, `user_properties`, `items`, and the `device` / `geo` / `traffic_source` structs | <https://support.google.com/analytics/answer/7029846> |
| `ga_session_id` is a session-start UNIX timestamp in **seconds**, unique only within a user → the session key must be `(user_pseudo_id, ga_session_id)` | <https://support.google.com/analytics/answer/9191807> |
| `event_timestamp` and `user_first_touch_timestamp` are **microseconds** since epoch (UTC) | export schema |
| `ecommerce.purchase_revenue` is **local currency**; `ecommerce.purchase_revenue_in_usd` is **USD** — two fields, two units | export schema |
| The export contains raw local currency, not reporting currency | <https://support.google.com/analytics/answer/9796179> |
| `traffic_source` is **first-user acquisition**; session scope is separate | <https://support.google.com/analytics/answer/11080067> |
| No advertising-cost table exists in the dataset → CAC/ROAS are impossible | dataset scope |

### 5.2 Deliberately recorded as `[UNRESOLVED]`

| Claim | Why it is not asserted |
|---|---|
| "`purchase_revenue` is `NULL` when the event currency differs from the property currency" | The documentation review could not support it. Both revenue fields are documented as "populated for purchase event only" with no currency-dependent NULL rule. Recorded as `[UNRESOLVED]` and given an **empirical test** instead: query 2 of `06_purchase_revenue_audit.sql` reports the NULL rate of each field separately. |
| "GA4 sessions also terminate at midnight" | The official session documentation reviewed states only the 30-minute inactivity timeout. `07_session_feasibility.sql` measures midnight-straddling sessions rather than assuming a boundary. |
| Whether `collected_traffic_source` / `session_traffic_source_last_click` / `privacy_info` / `batch_*` exist in the 2020 shards | Newer schema fields may post-date the export window. `00_project_settings.sql` includes a preflight to settle it. |

Resolving these by picking the more convenient reading would have been the easy path. They are left open because a wrong assumption in a funnel model is invisible until it is expensive.

### 5.3 Empirically blocked (`[BLOCKED — NO BIGQUERY ACCESS]`)

Event counts, unique user counts, daily volume, event taxonomy as observed, missing-`user_pseudo_id` rate, session-id collision rate, purchase-event counts, duplicate-`transaction_id` rate, revenue-field coverage, currency mix, item-array completeness, real shard inventory. Each has a named query. **No placeholder value was substituted for any of them.**

---

## 6. Verification evidence

### 6.1 Test suite

```text
.venv\Scripts\python.exe -m pytest tests
122 passed, 1 skipped in 0.40s
```

The single skip is `test_real_aggregate_fixtures_load_or_skip`, which is *designed* to skip: the repository intentionally ships no real aggregate under `tests/fixtures/`.

Coverage splits into two independent layers:

- **116 tests** on the quality library — positive and negative paths, plus error paths (wrong dtype, missing column, empty frame). Includes two bugs found during testing and fixed: pandas 3 `datetime64[us]` resolution breaking the nanoseconds-to-microseconds conversion, and object-dtype all-NULL columns slipping past numeric guards.
- **7 static contract tests** on the real `sql/exploration/*.sql` files: every file carries a `Purpose` + `Caveats` header, no bare `SELECT *`, every `events_*` wildcard read is accompanied by a `_TABLE_SUFFIX` filter, and no file contains `INSERT` / `UPDATE` / `DELETE` / `CREATE` / `DROP` / `MERGE` / `TRUNCATE` (comments stripped before the check).

### 6.2 Notebook

```text
.venv\Scripts\python.exe run_notebook.py notebooks/01_data_discovery.ipynb --env GROWTHSCOPE_NOTEBOOK_MODE=demo
    cells: 44 (20 code) | error cells: 0 | executed in: 3.2s | chart images: 4

.venv\Scripts\python.exe run_notebook.py notebooks/01_data_discovery.ipynb --env GROWTHSCOPE_NOTEBOOK_MODE=blocked --save
    cells: 44 (20 code) | error cells: 0 | executed in: 3.1s | chart images: 0
```

The notebook was executed in two different modes, and both runs completed with zero errors.

- The **`demo`** run exercises every code path with deterministic, clearly stamped synthetic data, and produces **4 rendered charts** — so the analysis code and the plotting code are both proven to work, not merely to import. The rendered PNGs were extracted and visually inspected (this is how the chart defects in §7 were found). Its outputs are **not** committed.
- The **`blocked`** run is the one whose outputs are saved in the repository. It prints the mode banner, the credentials problem, and the SQL that would run for each of the eight sections. It produces no numbers and no charts — correctly, because it has no data.

This separation is the point: the notebook is demonstrably executable without producing a single fake result.

### 6.3 Independent review

Agent E reviewed every artefact read-only against the repository's own rules and returned **GATE: YELLOW** with four blocking defects. All were fixed by the orchestrator — see §7. No link or anchor failures were found, and no secret or ignore-hygiene issues were found.

### 6.4 Static SQL validation

All eight `.sql` files: balanced parentheses and quotes, exactly one `-- [WINDOW]` marker per query, ASCII-only, no `SELECT *` over event tables, every `events_*` read shard-pruned. Syntax was checked statically; **no query was executed** and no byte figure exists anywhere in the repository.

---

## 7. Defects found in review and fixed

| # | Defect | Impact if shipped | Fix |
|---|---|---|---|
| 1 | `06_purchase_revenue_audit.sql` read `ecommerce.currency` | **The query would fail at runtime.** Currency is an `event_params` key; the `ecommerce` RECORD has no currency field. | Read `currency` from `event_params` via a correlated scalar subquery; the doc comment now explains why the record field does not exist |
| 2 | The "`purchase_revenue` is NULL under currency mismatch" claim was presented as `[DOCUMENTED]` in the notebook, `data_dictionary.md`, `metric_dictionary.md`, `architecture.md` and `06_*.sql` — while the research document recorded it as `[UNRESOLVED]` | The repository would have contradicted itself and stated an unsupported fact with authority, in a project whose whole premise is honest analytics | Downgraded to `[UNRESOLVED]` in all five places; reframed around the **real** documented trap (mixing units) and attached the empirical test |
| 3 | "~4.5M rows" appeared unsourced in `quality/__init__.py`, `quality/checks.py` and `data_quality_audit.md` | An invented figure in the codebase of a data-quality project | Replaced with non-numeric wording |
| 4 | The notebook asserted a GA4 **midnight session boundary** | False precision about a metric that changes session counts and therefore every conversion rate | Marked `[UNRESOLVED]`; the notebook now points to the query that measures it |
| 5 | Notebook saved outputs for queries 06 and 07 were empty (those files did not exist at first execution) | Committed outputs did not match the repository | Regenerated and re-executed after the SQL was complete; all eight cells now show their real statement |
| 6 | `00_project_settings.sql` claimed a full scan costs "~100x" a 3-day scan | Wrong by 3x in the file whose job is cost discipline | Corrected to ~30x (≈92 shards against 3) |
| 7 | `README.md` used "Purchase Conversion Rate" while the metric dictionary defines "Session Purchase Conversion Rate" | Metric-name drift between the front door and the definitions | Aligned to the dictionary names |
| 8 | `.env.example` omitted `GROWTHSCOPE_NOTEBOOK_MODE` and `GROWTHSCOPE_EXPORT_SAMPLE` | Two variables the notebook reads were undocumented, so the documented setup could not reproduce the documented modes | Added, with the mode semantics explained |
| 9 | The notebook forced `matplotlib.use("Agg")`, which silently suppressed **every chart** — the demo run produced 0 images | A notebook whose charts never appear looks fine when executed headlessly and is broken for a human reader; the failure mode is silent, not an exception | Switched to `%matplotlib inline`, which renders without a display server. Verified by extracting the rendered PNGs and inspecting them |
| 10 | The missing-identifier chart drew a single default-height bar (a solid block of colour), used raw column names as labels, and its synthetic-data stamp overlapped the title | Misleading chart and an obscured honesty warning | Bar height and axis padding now adapt to the number of bars, labels are humanised for display, and the stamp moved to the figure corner where nothing can overlap it |

Defect 1 would have been discovered on the first live run; defect 2 might never have been discovered, which is why the independent review was worth running.

---

## 8. Security and hygiene

| Check | Result |
|---|---|
| `.env` ignored, `.env.example` explicitly re-included | Confirmed via `git check-ignore -v` |
| `.venv/`, `__pycache__/`, `.pytest_cache/`, `.ipynb_checkpoints/` ignored | Confirmed |
| `data/raw/`, `data/tmp/` ignored; only aggregated data under `data/sample/` may be committed | Confirmed; `data/sample/` contains a policy README only |
| Credential-looking strings (API-key prefixes, PEM private-key headers, client-secret fields, token prefixes) | None found in any tracked-candidate file |
| Machine-specific absolute paths in documentation, code or notebook output | None; notebook output is rendered relative to the repository root and a regression scan returns zero hits |
| Raw user-level data published | None |

---

## 9. Acceptance criteria

| Criterion | Status |
|---|---|
| Project structure created | **PASS** |
| Python environment configured | **PASS** |
| Dependencies documented | **PASS** |
| `.gitignore` configured | **PASS** |
| No secrets exposed | **PASS** |
| Official dataset identified | **PASS** |
| Schema investigated | **PASS** (documentation) / **PARTIAL** (live verification) |
| Event taxonomy investigated | **PARTIAL / BLOCKED** |
| User and session identifiers assessed | **PASS** (structurally proven) / **PARTIAL** (collision rate unmeasured) |
| Purchase fields assessed | **PASS** (structure) / **PARTIAL** (coverage unmeasured) |
| Data limitations documented | **PASS** |
| SQL exploration files created | **PASS** (8 files, statically validated) |
| Jupyter notebook created | **PASS** |
| Notebook contains meaningful analysis | **PASS** |
| Initial data-quality checks implemented | **PASS** (10 checks, 116 tests) |
| Applicable automated tests executed | **PASS** (122 passed, 1 skipped by design) |
| README completed | **PASS** |
| Architecture documented | **PASS** |
| Data dictionary created | **PASS** |
| Metric dictionary created | **PASS** |
| Data-quality audit created | **PASS** |
| Code reviewed and integrated | **PASS** (independent review, 8 defects fixed) |
| Tests and verification results reported | **PASS** |
| Initial git commit created | **PASS** |
| GitHub remote status reported | **PASS** |
| Sprint 01 report completed | **PASS** |

**Overall: PARTIAL.** Every criterion that does not require the public dataset is met. The criteria marked `PARTIAL / BLOCKED` require one action that was not possible in this environment — a Google account with BigQuery Sandbox enabled — and are therefore reported as unmet rather than approximated.

---

## 10. Known limitations

1. **No live dataset execution.** No query was run; no observed value exists in the repository. This is the sprint's one real gap.
2. **`README.md` was extended, not rewritten.** It retains its original framing and vision. Where the original text described later sprints, it now distinguishes implemented from planned explicitly.
3. **Schema fields newer than the export window** are documented but flagged `[UNVERIFIED — needs BigQuery]`; the preflight in `00_project_settings.sql` settles them.
4. **The notebook's committed outputs are a `blocked` run.** A reader sees exactly what would execute and the reason it did not — by design.
5. **No CI workflow.** GitHub Actions was explicitly out of Sprint 01 scope; the suite is designed to run without BigQuery access or an editable install (`pyproject.toml` puts `src/` on the path), so wiring CI is a small, deferred task.
6. **Test coverage is proportional, not exhaustive.** The library's logic is thoroughly covered; the SQL is covered by static contract tests only, because executing it requires credentials.

---

## 11. Sprint 02 readiness

**Ready — with one prerequisite.**

The project can begin event normalisation and session modelling immediately once the prerequisite below is met, because the target shapes are already specified and the validation layer to check them already exists.

| Prerequisite | Owner | Why it blocks Sprint 02 |
|---|---|---|
| A Google Cloud project with BigQuery Sandbox enabled, and `gcloud auth application-default login` | Project owner | Every model in Sprint 02 is defined against observed data. Building `stg_ga4_events` on assumptions is exactly what Sprint 01 exists to prevent. |

Sprint 02's first hour is fully prescribed by Sprint 01:

1. Run `00_project_settings.sql` §C (shard preflight) — settles the shard inventory and the newer-schema-field question.
2. Dry-run every file and record bytes processed in the results log.
3. Execute `01` → `07` over `2020-11-01` … `2020-11-03` and record results with Job IDs.
4. Re-run the notebook in `live` mode; replace each `[BLOCKED]` row in §5.3 and in `docs/data_quality_audit.md` with the measured value.
5. Resolve the three `[UNRESOLVED]` claims in §5.2 empirically — specifically the currency-NULL rate (query 2 of `06`) and midnight straddling (query 6 of `07`).
6. Then, and only then, build the models: `stg_ga4_events` → `int_sessions` → `int_session_funnel` → `fct_purchases`, with `check_funnel_monotonicity` and `check_purchase_transaction_duplicates` gating them.

Models not to build yet: any mart, any dashboard, any cohort or attribution analysis. Sprint 02 is one session model built correctly.

---

## 12. Reproducing this sprint

```bash
git clone https://github.com/nnurkass/growthscope.git
cd growthscope
python -m venv .venv
.venv\Scripts\activate                 # Windows PowerShell
# source .venv/bin/activate            # macOS / Linux
pip install -r requirements.txt
python -m pytest                       # expect: 122 passed, 1 skipped
jupyter lab notebooks/01_data_discovery.ipynb
```

To go beyond structural verification:

```bash
gcloud auth application-default login
# PowerShell: $env:GOOGLE_CLOUD_PROJECT="your-project-id"
# bash:       export GOOGLE_CLOUD_PROJECT=your-project-id
export GROWTHSCOPE_NOTEBOOK_MODE=live
```

Cost guardrails already in place: a three-day window, mandatory `_TABLE_SUFFIX` shard pruning, projection instead of `SELECT *`, and `maximum_bytes_billed` defaulting to 2 GB so an accidental full scan fails instead of billing.

---

*GrowthScope is an independent portfolio project. It is not affiliated with, endorsed by, or sponsored by Google. The GA4 sample dataset is used under the terms of its public dataset licence.*
