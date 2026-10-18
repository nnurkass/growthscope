# Dataset Research — GA4 Obfuscated Sample E-commerce Dataset

**Project:** GrowthScope — Marketing & Growth Intelligence for E-commerce
**Stage:** Sprint 01 — Project Foundation & Data Discovery
**Document type:** Data source research (desk research against official documentation)
**Owner of semantics for later stages:** see `docs/data_limitations.md` (Sprint 02+)
**Author context:** Subagent A — Data Source Researcher

> **Research integrity statement.** No query was executed while writing this document. There is no
> BigQuery access in the authoring environment: `gcloud` / `bq` are not installed, there are no
> Application Default Credentials, and the BigQuery REST metadata endpoint was not reachable from this
> machine (`GET https://bigquery.googleapis.com/v2/projects/bigquery-public-data/datasets/ga4_obfuscated_sample_ecommerce/tables` returned a non-2xx status — **[BLOCKED — NO BIGQUERY ACCESS]**).
> **Therefore no row counts, date ranges, NULL rates, value distributions, or observed numbers appear
> in this document.** Every statement below is either quoted from a citable public document or
> explicitly flagged as unverified. Where this document reasons beyond the documentation, it says so.

---

## 0. Verification legend

These five badges are used consistently throughout. Every factual claim carries exactly one.

| Badge | Meaning | Evidence requirement |
|---|---|---|
| `[DOCUMENTED]` | Stated in official Google documentation (developers.google.com, support.google.com, cloud.google.com, console.cloud.google.com). | Inline source ID (`R#`, see §1) resolving to a full URL. |
| `[UNVERIFIED]` | Plausible and consistent with documentation, but **not confirmed here** because it requires a live query or a dataset-schema read. Must be confirmed before it is relied on. | A concrete verification query in §14. |
| `[ASSUMPTION]` | Author reasoning or inference, not a documentation claim. Confidence level is stated in the text. | Explicit reasoning shown. |
| `[UNRESOLVED]` | Documentation is silent, ambiguous, contradictory, or third-party only. Do not build on it. | Flagged in §12 (Open questions) and §13 (Sprint 02). |
| `[BLOCKED — NO BIGQUERY ACCESS]` | Cannot be answered in the authoring environment at all. | Blocked by tooling/credentials, not by analysis. |

Source IDs (`R1`…`R18`, `N1`…`N6`) are defined in §1 with full URLs.

---

## 1. Official references

### 1.1 Primary official sources

| ID | URL | What it confirms |
|---|---|---|
| **R1** | https://developers.google.com/analytics/bigquery/web-ecommerce-demo-dataset | The canonical page for this dataset: existence, provenance (Google Merchandise Store), scope ("three months from 2020-11-01 to 2021-01-31"), obfuscation limitations, prerequisites, and the canonical `events_*` query. *Last updated 2026-08-19 UTC.* |
| **R2** | https://support.google.com/analytics/answer/7029846 | The GA4 BigQuery Export schema: dataset/table naming, every top-level column, and the definitions of `event_params`, `items`, `item_params`, `user_properties`, `privacy_info`, `user_ltv`, `device`, `geo`, `app_info`, `collected_traffic_source`, `session_traffic_source_last_click`, `traffic_source`, `stream_id`, `platform`, `ecommerce`. This is the authoritative field dictionary. |
| **R2b** | https://developers.google.com/analytics/bigquery/event-schema | Developer-site alias of **R2**. Fetched and confirmed to serve the identical schema content; use either URL. |
| **R3** | https://support.google.com/analytics/answer/10937659 | Help Center entry "[GA4] Google Analytics 4-property sample dataset for BigQuery". Contains no independent content — it is a stub that links to **R1**. |
| **R4** | https://developers.google.com/analytics/bigquery/basic-queries | Official sample queries **that run against this dataset**. Critically, it documents that `batch_page_id`, `batch_ordering_id` and `batch_event_index` are **not** in the sample dataset schema. Also demonstrates `UNNEST(items)` and `event_params.value.{int,float,double}_value` usage on this dataset. |
| **R5** | https://developers.google.com/analytics/bigquery/advanced-queries | Official advanced queries on this dataset: extracting `ga_session_id` and `ga_session_number` from `event_params`, `UNNEST(items)` with `items.quantity`, and a real GMS product name (`'Google Navy Speckled Tee'`). |
| **R6** | https://support.google.com/analytics/answer/9191807 | Sessions: definition, 30-minute default inactivity timeout (and how to change it), how `ga_session_id` and `ga_session_number` are generated, per-event association, and the explicit guidance to join `user_pseudo_id` **with** `session_id` for a unique session key. Also: session attribution comes from the `session_start` event (gclid, UTM, referrer), and session metrics are HLL++-estimated in the UI but exact in BigQuery. |
| **R7** | https://support.google.com/analytics/answer/9756891 | Default channel group: the three scoped variants (event / session / user), the channel list, and the rule definitions (manual-traffic rules plus Google Ads, SA360, DV360, CM360, and Merchant Center rules). |
| **R8** | https://support.google.com/analytics/answer/11080067 | Scope semantics in GA4: user-scoped ("First user …") vs session-scoped ("Session …") vs event-scoped dimensions, and that user- and session-scoped dimensions use paid-and-organic last-click. |
| **R9** | https://support.google.com/analytics/answer/9796179 | Currency: monetization metrics, that `currency` is required for revenue metrics when `value` is sent, and — the load-bearing sentence — *"In BigQuery export, the raw transaction values included in the data are in local currency, and aren't based on the reporting currency."* |
| **R10** | https://support.google.com/analytics/answer/11397207 | GA4 web cookies: the `_ga` and `_ga_<container-id>` first-party cookies, the 2-year default expiry, and browser caps ("maximum of 400 days for Chrome and 7 days for Safari") when a user does not return. |
| **R11** | https://support.google.com/analytics/answer/13578783 | BigQuery vs. GA4 UI reconciliation: *"GA4 only exports data based on Device ID to BigQuery"*, expected 2–5% event-count discrepancy, and timezone/reporting-identity caveats. |
| **R12** | https://support.google.com/analytics/answer/6367342 | The GA4 **demo account** (Google Merchandise Store + Flood-It!). Data is obfuscated; the demo account lacks export functionality, lacks the device-ID dimension and the User Exploration; the Analytics Data API cannot be used with it. |
| **R13** | https://support.google.com/analytics/answer/9234069 | Automatically collected events: the `session_start` and `first_visit` parameter lists, and the parameters collected by default with every event (web: `language`, `page_location`, `page_referrer`, `page_title`, `screen_resolution`). |
| **R14** | https://developers.google.com/analytics/devguides/collection/ga4/ecommerce | The ecommerce event reference for `items[]`: the prescribed item parameter inventory, default `quantity = 1`, `item_id`/`item_name` requirement, up to 200 elements in `items`, up to 27 custom item parameters. Includes the `purchase` and `refund` payload examples. |
| **R15** | https://developers.google.com/analytics/devguides/collection/ga4/set-up-ecommerce | A worked `purchase` event: exact parameter names, the parameter → GA4 dimension → value mapping table, and the statement that `transaction_id` is what prevents duplicate counting of the same purchase. |
| **R16** | https://developers.google.com/analytics/devguides/collection/ga4/user-id | `user_id` semantics: send only for signed-in users, send `null` on sign-out, never as a user property or event parameter; raw `user_id` values are best obtained from the BigQuery export. |
| **R17** | https://cloud.google.com/bigquery/public-data | The public dataset program: access via Cloud console, `bq` CLI, REST API and client libraries; `US` multi-region location; 1 TB/month free query tier. |
| **R18** | https://support.google.com/analytics/answer/12769371 | The separate **user-data** export (Pseudo ID / User ID tables). Different artefact from the events export — documented here to prevent conflation. |

### 1.2 Non-official sources used (clearly labelled)

These were fetched/searched but are **not** Google documentation. They are cited only where no official
statement exists, and are always marked `[UNRESOLVED]` or `[ASSUMPTION]`.

| ID | URL | Why it is here | Status |
|---|---|---|---|
| **N1** | https://medium.com/@maltug23/ga4-bigquery-export-evolution-of-traffic-sources-and-correct-analysis-strategies-ea79b7b72ba3 | Claims `collected_traffic_source` was added to the export schema in June 2023. | Unofficial |
| **N2** | https://www.ga4bigquery.com/how-to-fix-the-major-ga4-bigquery-export-misattribution-part-3-use-the-session_traffic_source_last_click-record/ | Claims `session_traffic_source_last_click` was added in July 2024. | Unofficial |
| **N3** | https://tanelytics.com/ga4-bigquery-session-traffic_source/ | Claims `collected_traffic_source` from June 2023 and `session_traffic_source_last_click` on 2024-07-17, updated 2024-10-09. | Unofficial |
| **N4** | https://medium.com/@dmitrijs.gizdevans/profiling-and-flattening-ga4-data-in-bigquery-a-step-by-step-walkthrough-46d7f9e629a5 | Claims "92 daily tables, ~4.3M events". | Unofficial, unverified |
| **N5** | https://observablehq.com/@observablehq/google-merchandise-sales-data | An unofficial, reshaped CSV/Parquet extract derived from this dataset (see §11). | Unofficial |
| **N6** | https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/bundles/ga4/datasets/ga4_obfuscated_sample_ecommerce.md | Google-hosted repository, but the file is **machine-generated** (`generated.by: reference_agent/gemini-3.5-flash`). Contains a contradiction and at least one definitely wrong type. **Do not treat as authority.** See §11.3. | Google-hosted, AI-generated |

---

## 2. Dataset identity & availability

| Claim | Badge | Evidence |
|---|---|---|
| The dataset exists, is official, and is published through the **BigQuery Public Datasets program**. | `[DOCUMENTED]` | R1 — "The `ga4_obfuscated_sample_ecommerce` dataset available through the BigQuery Public Datasets program…" |
| Fully-qualified reference is `bigquery-public-data.ga4_obfuscated_sample_ecommerce`. | `[DOCUMENTED]` | R1, R4, R5 — every official sample query uses `` `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*` ``. |
| The dataset contains **a sample of obfuscated BigQuery event export data** (not a complete, unmodified export). | `[DOCUMENTED]` | R1 — "contains a sample of obfuscated BigQuery event export data for three months". The word "sample" is Google's. |
| Provenance is the **Google Merchandise Store** (shop.googlemerchandisestore.com), which uses GA4's standard web ecommerce implementation **and** enhanced measurement. | `[DOCUMENTED]` | R1. |
| The data is **obfuscated** and contains placeholder values including `<Other>`, `NULL`, and `''`; "internal consistency of the dataset might be somewhat limited." | `[DOCUMENTED]` | R1 (Limitations section). |
| The dataset **cannot be compared** to the GA4 Demo Account for the Google Merchandise Store, because the underlying data is different. | `[DOCUMENTED]` | R1 — explicit sentence. This kills a very common mistake: the demo account and this dataset are two separate things. |
| Access requires a Google Cloud project with the BigQuery API enabled; **BigQuery Sandbox** or the free usage tier is sufficient for exploration and the sample queries. | `[DOCUMENTED]` | R1 (Pre-requisite). |
| Public datasets live in the `US` multi-region; cross-region joins/writes with sample tables are not possible. | `[DOCUMENTED]` | R17. |
| The dataset is a **real GA4 event export structure**, i.e. the same schema family as a customer's own `analytics_<property_id>` dataset. | `[DOCUMENTED]` | R2 (table/column definitions) + R1 (it is described as BigQuery event export data). |
| The dataset's tables are **live and queryable today**, with no announced deprecation. | `[UNVERIFIED]` | R1 was last updated 2026-08-19 and still documents it; but no row-count/schema check was possible here. See §14 Query A. |

**Consequence for the project.** GrowthScope may describe this as an official Google public dataset built
from the Google Merchandise Store's GA4 implementation, queried through BigQuery. It may **not** describe
it as "the store's production data", "the GA4 demo account", or a complete export. `[ASSUMPTION]` —
wording discipline derived directly from R1's limitations.

---

## 3. Date coverage

| Claim | Badge | Evidence |
|---|---|---|
| Documented coverage is **2020-11-01 to 2021-01-31 inclusive** — three months. | `[DOCUMENTED]` | R1 — "a sample of obfuscated BigQuery event export data for three months from 2020-11-01 to 2021-01-31." |
| The **last** daily shard is `events_20210131`. | `[DOCUMENTED]` (strong) | R1 links the console deep-link to `t=events_20210131`, i.e. Google names that table directly. R5 queries `_TABLE_SUFFIX BETWEEN '20201101' AND '20210131'` against this dataset. |
| The **first** daily shard is `events_20201101`. | `[DOCUMENTED]` (strong) | R4 and R5 both use `_TABLE_SUFFIX BETWEEN '20201101' AND …` against this dataset. Combined with the documented "from 2020-11-01" this is the first day. |
| Both endpoints — not just the interior — are populated with events. | `[UNVERIFIED]` | A `_TABLE_SUFFIX BETWEEN` filter does not prove the first/last day has rows; `_TABLE_SUFFIX` filtering can match zero tables without erroring. See §14 Query A/C. |
| The window contains **92 calendar days**, i.e. at most 92 daily shards. | `[ASSUMPTION]` (arithmetic, high confidence) | 30 (Nov) + 31 (Dec) + 31 (Jan) = 92. N4 independently claims "92 daily tables" and "~4.3M events" — consistent with the arithmetic, but N4 is unofficial and was not verifiable, so the event count remains `[UNVERIFIED]`. |
| There is **no intraday** data for this dataset. | `[ASSUMPTION]` (high confidence) | R2 states `events_intraday_YYYYMMDD` is a streaming-export artefact deleted at end of day; R1 documents only the `events_*` family. No `events_intraday_*` shard can survive for 2020–2021. |
| Daily tables for a live property are updated for up to **3 days** for late-arriving events; the sample dataset is historical and therefore closed. | `[DOCUMENTED]` for the rule (R2); `[ASSUMPTION]` that the sample dataset is fully settled | R2. |
| **Do not claim seasonality or year-over-year effects.** The window is one contiguous 92-day block covering a single holiday season, with no prior-year comparison and no post-January tail. | `[ASSUMPTION]` (high confidence) | Direct consequence of a single 92-day window. Any "Q4 pattern" or "January drop-off" statement is a within-window observation, not a seasonal finding. |

### 3.1 Contradiction found — flagged, not resolved

A **Google-hosted but machine-generated** catalogue file in `GoogleCloudPlatform/knowledge-catalog` (N6)
summarises the *dataset* as spanning "**November 1, 2020, to January 1, 2021**", while its sibling *table*
file in the same repository states the shard range as `events_20201101` **through `events_20210131`**.
Those two statements disagree. `[UNRESOLVED]` — the primary documentation (R1) and both official query
cookbooks (R4, R5) all point to **2021-01-31**, so the "January 1" phrasing is treated as an error in an
AI-generated summary, not as a competing fact. This is recorded because it shows exactly why
machine-generated catalogues must never be used to establish a fact of record. See §11.3.

---

## 4. Table / shard naming

| Claim | Badge | Evidence |
|---|---|---|
| GA4 exports one dataset per property, named `analytics_<property_id>`. | `[DOCUMENTED]` | R2. The public sample is instead published under the fixed name `ga4_obfuscated_sample_ecommerce`. |
| Daily tables are named `events_YYYYMMDD`. | `[DOCUMENTED]` | R2 — "Within each dataset, a table named `events_YYYYMMDD` is created each day…". |
| Streaming tables are named `events_intraday_YYYYMMDD` and are deleted at end of day. | `[DOCUMENTED]` | R2. Not expected in the sample dataset (see §3). |
| Wildcard querying is the intended access pattern for the daily-shard family: `` `…ga4_obfuscated_sample_ecommerce.events_*` ``. | `[DOCUMENTED]` | R1, R4, R5. |
| Date filtering should use the `_TABLE_SUFFIX` pseudo-column. | `[DOCUMENTED]` | R4 — dedicated "Query a specific date range" section linking to BigQuery wildcard-table docs. |
| Practical implication: a naive `SELECT * FROM …events_*` scans **every** shard. `_TABLE_SUFFIX` pruning is the primary cost-control mechanism (the free tier gives 1 TB/month — R17). | `[ASSUMPTION]` (standard BigQuery behaviour) | R4, R17. |
| Practical implication: the schema is **per daily table**. Columns added to the GA4 export schema after a table was created are not back-filled into it. | `[ASSUMPTION]` (high confidence, structural) | Follows from R2's per-day table model. This is the mechanism behind the column-presence uncertainty in §5 and §9. |

---

## 5. Event-level schema (top-level columns)

**Read this before using the table.** R2 documents the **current** GA4 BigQuery export schema. The public
sample dataset contains **2020-11 / 2021-01** shards, exported with the schema as it existed then. Google
publishes **no per-shard schema snapshot** for this dataset. Therefore the "In 2020-era shards?"
column is `[DOCUMENTED]` **only** where an official sample query against this dataset proves the field, and
`[UNVERIFIED]` / `[ASSUMPTION]` everywhere else. Do not present any `[UNVERIFIED]` row as fact.

Source for every row in this table: **R2** (https://support.google.com/analytics/answer/7029846), unless a
different source ID is stated. Types are from R2 verbatim.

| Column | Type | Mode | Purpose | In 2020-era shards? |
|---|---|---|---|---|
| `event_date` | STRING | NULLABLE | Event date, `YYYYMMDD`, in the property's registered timezone. | `[DOCUMENTED]` — used in official queries on this dataset (R4) |
| `event_timestamp` | INTEGER | NULLABLE | Event time in **microseconds, UTC**, as received by GA. Multiple events can share a timestamp if sent in one request. | `[DOCUMENTED]` — R4 |
| `event_previous_timestamp` | INTEGER | NULLABLE | Microsecond timestamp of the previous event. | `[UNVERIFIED]` |
| `event_name` | STRING | NULLABLE | The event name. | `[DOCUMENTED]` — R4 |
| `event_value_in_usd` | FLOAT | NULLABLE | Currency-converted USD value of the event's `value` parameter. | `[UNVERIFIED]` |
| `event_bundle_sequence_id` | INTEGER | NULLABLE | Sequential ID of the upload bundle. | `[UNVERIFIED]` |
| `event_server_timestamp_offset` | INTEGER | NULLABLE | Offset between collection time and upload time, in micros. | `[UNVERIFIED]` |
| `batch_event_index` | INTEGER | NULLABLE | Order of the event within a batch on the device. | **`[DOCUMENTED]` ABSENT** — R4: "The sample dataset schema does not contain the `batch_page_id`, `batch_ordering_id`, or `batch_event_index` fields." |
| `batch_ordering_id` | INTEGER | NULLABLE | Monotonic counter incremented per network request from a page. | **`[DOCUMENTED]` ABSENT** — R4 |
| `batch_page_id` | INTEGER | NULLABLE | Sequential page number within an engagement. | **`[DOCUMENTED]` ABSENT** — R4 |
| `event_params` | RECORD | **REPEATED** | Event-scoped key/value parameters. | `[DOCUMENTED]` — R4, R5 |
| `user_id` | STRING | NULLABLE | The ID assigned to a signed-in user. | `[DOCUMENTED]` — referenced in official queries on this dataset using `user_id` (R4, R5) |
| `user_pseudo_id` | STRING | NULLABLE | Pseudonymous id assigned on first visit/open. | `[DOCUMENTED]` — R4, R5 |
| `user_first_touch_timestamp` | INTEGER | NULLABLE | Microsecond timestamp of the user's very first visit/open. | `[UNVERIFIED]` |
| `user_properties` | RECORD | **REPEATED** | User-property key/value pairs + `set_timestamp_micros`. | `[UNVERIFIED]` |
| `privacy_info` | RECORD | NULLABLE | Consent state: `ads_storage`, `analytics_storage`, `uses_transient_token` (values `Yes` / `No` / `Unset`). | `[UNVERIFIED]` |
| `user_ltv` | RECORD | NULLABLE | `revenue`, `currency`. Not populated in intraday tables. | `[UNRESOLVED]` (in the *events* export) — see §11.3 |
| `device` | RECORD | NULLABLE | `category`, `mobile_brand_name`, `mobile_model_name`, `mobile_marketing_name`, `mobile_os_hardware_model`, `operating_system`, `operating_system_version`, `vendor_id`, `advertising_id`, `language`, `time_zone_offset_seconds`, `is_limited_ad_tracking`, **`web_info.{browser, browser_version, hostname}`**. | `[UNVERIFIED]` |
| `geo` | RECORD | NULLABLE | `continent`, `sub_continent`, `country`, `region`, `metro`, `city` — derived from IP. | `[UNVERIFIED]` |
| `app_info` | RECORD | NULLABLE | `id`, `firebase_app_id`, `install_source`, `version`. | `[ASSUMPTION]` present-but-empty for a web property — see note below |
| `traffic_source` | RECORD | NULLABLE | **First-user** acquisition: `name`, `medium`, `source`. | `[UNVERIFIED]` |
| `collected_traffic_source` | RECORD | NULLABLE | Traffic source observed on the collected event: `manual_campaign_id`, `manual_campaign_name`, `manual_source`, `manual_medium`, `manual_term`, `manual_content`, `manual_creative_format`, `manual_marketing_tactic`, `manual_source_platform`, `gclid`, `dclid`, `srsltid`. Also carries `manual_source_platform` (further per-source-platform subfields exist for the ad platforms). | `[ASSUMPTION]` **ABSENT/NULL** — added to the schema circa June 2023 per unofficial sources (N1, N3); a 2020-era shard is structurally older. Must be verified. |
| `session_traffic_source_last_click` | RECORD | NULLABLE | Last-click-attributed **session** traffic source across Google Ads and manual contexts (`manual_campaign.*`, `google_ads_campaign.*`, `dv360_campaign.*`, `cm360_campaign.*`, `sa360_campaign.*`, `cross_channel_campaign.*`). | `[ASSUMPTION]` **ABSENT/NULL** — introduced 2024 per unofficial sources (N2, N3); structurally cannot be in a 2020-era shard. Must be verified. |
| `stream_id` | STRING | NULLABLE | Numeric ID of the data stream. | `[UNVERIFIED]` |
| `platform` | STRING | NULLABLE | Data-stream platform: `Web`, `IOS`, `Android`. | `[UNVERIFIED]` — expected `Web` throughout |
| `is_active_user` | BOOLEAN | NULLABLE | Whether the user was active at any point in the calendar day. Populated **only** in daily (`events_YYYYMMDD`) tables. | `[UNRESOLVED]` — plausibly added after 2020 |
| `ecommerce` | RECORD | NULLABLE | Purchase/refund monetary and order fields — see §9. | `[UNVERIFIED]` |
| `items` | RECORD | **REPEATED** | Item-level fields — see §9. | `[DOCUMENTED]` — R4 and R5 both `UNNEST(items)` against this dataset |
| `publisher` | RECORD | NULLABLE | AdMob ad-revenue fields (early access). | `[ASSUMPTION]` ABSENT for a web property |
| *anything else* | — | — | — | `[UNVERIFIED]` — enumerate, do not guess (§14 Query B) |

**Note on `app_info` and `publisher`.** `[ASSUMPTION]` (high confidence): the Google Merchandise Store is
a web property (R1), so `app_info` and `publisher` should be present in the schema but empty/null; `platform`
should be `Web`. This is reasoning from provenance, not a documentation claim, and must be confirmed.

### 5.1 Event-name inventory

| Claim | Badge | Evidence |
|---|---|---|
| `page_view`, `session_start`, `purchase` and `add_to_cart` all exist in this dataset. | `[DOCUMENTED]` (strong) | R4 runs a query on this dataset filtered to `event_name IN ('page_view', 'session_start', 'purchase')`, a query filtered to `'add_to_cart'`, and a query on `event_name = 'purchase'`. Google describes them as producing valid results on the sample table. |
| `first_visit` exists (used to identify new users). | `[DOCUMENTED]` (strong) | R4's "User count, new users, and returning users" query filters `event_name IN ('first_visit', 'first_open')` on this dataset. |
| `in_app_purchase` exists in this dataset. | `[UNRESOLVED]` | Google's sample queries *include* it in a filter list, but these are generic GA4 templates (they also include `first_open`, an app-only event, on a web dataset). The inclusion is defensive coding, not evidence. |
| Additional funnel steps `view_item`, `view_item_list`, `begin_checkout`, `add_payment_info`, `add_shipping_info`, `select_item`, `view_promotion`, `select_promotion`, `refund`, and enhanced-measurement events (`scroll`, `click`, `file_download`, `video_*`, `form_*`) exist. | `[UNVERIFIED]` | All are standard GA4 ecommerce / enhanced-measurement events (R13, R14) and the store uses enhanced measurement (R1), but no official query on this dataset proves any specific one. The GrowthScope funnel assumes `view_item`, `add_to_cart`, `begin_checkout`, `purchase` — **that assumption must be tested before any funnel metric is published.** See §14 Query D. |

---

## 6. Nested & repeated structures

GA4 export is **not** a flat table. R2 defines these nested (`RECORD`) and repeated (`REPEATED`) structures.

| Structure | Shape | Badge |
|---|---|---|
| `event_params` | REPEATED RECORD → inner `value` RECORD | `[DOCUMENTED]` R2, R4, R5 |
| `items` | REPEATED RECORD → inner `item_params` REPEATED RECORD | `[DOCUMENTED]` R2; `UNNEST(items)` used on this dataset in R4, R5 |
| `user_properties` | REPEATED RECORD → inner `value` RECORD | `[DOCUMENTED]` R2 |
| `device` | RECORD → inner `web_info` RECORD | `[DOCUMENTED]` R2 |
| `geo` | RECORD (flat) | `[DOCUMENTED]` R2 |
| `traffic_source` | RECORD (flat) | `[DOCUMENTED]` R2 |
| `app_info` | RECORD (flat) | `[DOCUMENTED]` R2 |
| `collected_traffic_source`, `session_traffic_source_last_click` | RECORD (partly nested) | `[DOCUMENTED]` R2 *as current schema*; presence in this dataset `[UNRESOLVED]` |
| `ecommerce` | RECORD (flat) | `[DOCUMENTED]` R2 |

### 6.1 How the export represents one event

R2 documents explicitly that *"Data for a single event may be represented in one or multiple rows, depending
on whether it contains repeated RECORDS."* `[DOCUMENTED]` R2, with a worked `page_view` example table showing
one base row plus one row per `event_params` entry. The same applies to `items` and `user_properties`.

### 6.2 Performance implication of `UNNEST`

| Claim | Badge |
|---|---|
| `UNNEST` on a REPEATED field **multiplies rows**: one `purchase` event with three items becomes three rows. Any aggregate over unnested data counts events/items, not the original event rows. | `[DOCUMENTED]` R2 (the multi-row representation) + `[ASSUMPTION]` (the counting consequence) |
| Because of that, `JOIN`ing two unnested arrays in one query can produce a **cross-product** and inflate metrics. The safe patterns are (a) a scalar subquery — `(SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'x')` as Google itself does in R4/R5 — or (b) unnest **one** array per CTE and aggregate before joining. | `[ASSUMPTION]` (standard BigQuery semantics; R4/R5 demonstrate the scalar-subquery pattern) |
| Every `UNNEST` also expands the data scanned by the `value` columns it touches, because BigQuery's columnar storage must decompress the nested column. Selecting only the needed subfields (`value.int_value`, not the whole `event_params`) keeps cost down. | `[ASSUMPTION]` (BigQuery columnar/storage model) |
| Unnesting `items` on `event_name = 'purchase'` and summing `price * quantity` **at the same time as** summing `ecommerce.purchase_revenue` double-counts revenue: the revenue field is already order-level. Pick **either** order-level (`ecommerce.*`, no unnest) **or** item-level (`items.*`, unnested) as the revenue basis — never both in one total. | `[ASSUMPTION]` (high confidence) — supported by R2's field definitions ("`items.item_revenue` … populated for purchase events only", "`ecommerce.purchase_revenue` … represented in local currency") |
| Google's own guidance for the item-level case is to aggregate with `ARRAY_AGG`/`UNNEST` inside a CTE and then aggregate — the "optimized" query in R5. | `[DOCUMENTED]` R5 |

---

## 7. `event_params` deep dive

### 7.1 Structure

| Element | Type | Documented meaning | Badge |
|---|---|---|---|
| `event_params` | RECORD, REPEATED | "can store campaign-level and contextual event parameters as well as any user-defined event parameters… repeated for each key that is associated with an event." | `[DOCUMENTED]` R2 |
| `event_params.key` | STRING | The parameter name. | `[DOCUMENTED]` R2 |
| `event_params.value` | RECORD | A record holding the parameter's value. | `[DOCUMENTED]` R2 |
| `event_params.value.string_value` | STRING | Populated for string parameters (URLs, campaign names…). | `[DOCUMENTED]` R2 |
| `event_params.value.int_value` | INTEGER | Populated for integer parameters. | `[DOCUMENTED]` R2 |
| `event_params.value.double_value` | FLOAT | Populated for double parameters. | `[DOCUMENTED]` R2 |
| `event_params.value.float_value` | FLOAT | *"This field is not currently in use."* | `[DOCUMENTED]` R2 |
| `items[].item_params` | RECORD, REPEATED | Same key/value shape for **item-scoped custom** parameters. R2: "predefined item parameters like `item_id`, `item_name` etc, are not included here, instead they are exported as explicit fields." | `[DOCUMENTED]` R2 |
| The `set` of parameters is unique to each implementation — you must enumerate it, not assume it. | — | "The set of parameters stored in the event_params RECORD is unique to each implementation." | `[DOCUMENTED]` R2, R4 (R4 provides the event-parameter-list query) |

**Important practical tension `[DOCUMENTED]`:** R2 says `float_value` is *not currently in use*, yet
Google's own sample query for this dataset (R4) reads the `value` parameter as
`COALESCE(value.int_value, value.float_value, value.double_value)`, and R5 does the same for `ga_session_id`
and `value`. The defensible engineering rule is therefore: **always `COALESCE` all three numeric columns**
(never read only `int_value`), and treat `float_value` as legacy-but-possibly-populated. This is a
documentation inconsistency worth knowing before writing revenue SQL.

### 7.2 Which value column to read for the parameters that matter

| Parameter key | Look for it on | Value column to read | Badge |
|---|---|---|---|
| `ga_session_id` | every event in a session | `value.int_value` (a UNIX timestamp in **seconds** — R6) | `[DOCUMENTED]` R5, R6 |
| `ga_session_number` | every event in a session | `value.int_value` | `[DOCUMENTED]` R5 |
| `page_location`, `page_referrer`, `page_title` | `page_view`, `session_start`, `first_visit` | `value.string_value` | `[DOCUMENTED]` R2, R4, R13 |
| `value` (event monetary value) | `purchase`, `refund`, and other monetised events | `COALESCE(int_value, float_value, double_value)` | `[DOCUMENTED]` R4 |
| `currency` | events carrying `value` | `value.string_value` | `[DOCUMENTED]` R9 ("If you set `value` in your event data, then `currency` is required for revenue metrics") |
| `transaction_id`, `tax`, `shipping`, `coupon`, `payment_type` | see §9 for the precise event mapping | `string_value` / numeric columns per R14 example payloads | `[DOCUMENTED]` R14 |
| `engagement_time_msec` | engagement events | numeric | `[DOCUMENTED]` R13 |
| `ignore_referrer`, `traffic_type` | `session_start`, `first_visit` | `string_value` (booleans are transported as strings) — **the storage column for these two is `[UNRESOLVED]`** | `[DOCUMENTED]` R13 for the parameter list; column mapping `[UNRESOLVED]` |
| `language`, `screen_resolution` | all web events | `string_value` | `[DOCUMENTED]` R13 |
| Custom / measurement-protocol parameters | varies | varies — enumerate first | `[DOCUMENTED]` R2 |

**Why `ga_session_id` and `ga_session_number` live inside `event_params`.** `[DOCUMENTED]` R2 + R6:
`event_params` is the schema's extension point for per-event key/value data, and GA attaches the session
identifiers to **each event** in the session as ordinary event parameters rather than as top-level columns.
R6 states they are generated with the `session_start` event and then "associated with each event in a
session automatically via gtag.js and the Google Analytics for Firebase SDK" — with the documented
exception that they are *not* attached automatically for Measurement Protocol or Data Import events.
R5's official query shows the extraction pattern. `[ASSUMPTION]` (consequence): any event lacking a
`ga_session_id` param is not attributable to a session, so it must be excluded from session metrics **and
its share reported** rather than silently dropped.

---

## 8. User identification

### 8.1 `user_pseudo_id`

| Claim | Badge | Evidence |
|---|---|---|
| `user_pseudo_id` is the "pseudonymous id (e.g., app instance ID) for the user. A unique identifier that is assigned to a user when they first open the app or visit the site." | `[DOCUMENTED]` | R2 |
| It is **cookie/device-scoped**, not a person. GA4 web tags use first-party cookies (`_ga`, `_ga_<container-id>`, 2-year default) to distinguish users and sessions. | `[DOCUMENTED]` | R10 |
| Cookie lifetime is capped by the browser: **max 400 days in Chrome, 7 days in Safari** for non-returning users. | `[DOCUMENTED]` | R10 |
| BigQuery export is **Device-ID based** ("GA4 only exports data based on Device ID to BigQuery"), so BigQuery user counts are device-scoped and will not match UI counts computed under a blended reporting identity. | `[DOCUMENTED]` | R11 |
| Consequently `user_pseudo_id` **can change for the same human**: new device, cleared cookies, a different browser, and the shorter Safari cookie window all produce a new `user_pseudo_id`. | `[ASSUMPTION]` (high confidence) | Direct consequence of R2 + R10 + R11. Google does not document a per-scenario list. |
| Therefore "users" in GrowthScope means **pseudonymous devices/browsers**, and any cross-period "same user returned" claim is an upper/lower-bound estimate, not a fact. | `[ASSUMPTION]` | Consequence of the above. |

### 8.2 `user_id`

| Claim | Badge | Evidence |
|---|---|---|
| `user_id` is "The unique ID assigned to a user" — i.e. your own identifier for a **signed-in** user. | `[DOCUMENTED]` | R2; R16 |
| It should be sent only when the user is signed in; never for users who have never signed in; `null` on sign-out. | `[DOCUMENTED]` | R16 |
| Raw `user_id` values are normally only available in the BigQuery export, not as a UI dimension. | `[DOCUMENTED]` | R16 |
| For a demo e-commerce store, the overwhelming majority of sessions are anonymous, so `user_id` is expected to be empty for most rows. | `[ASSUMPTION]` (high confidence) | Consequence of R16 — Google Merchandise Store is a public storefront with no documented forced login. **Not verified.** |
| The GA4 **demo account** excludes the device-ID dimension entirely, which is a further reason not to confuse it with this dataset. | `[DOCUMENTED]` | R12 |

**Project rule (for later sprints):** `user_pseudo_id` is the only universally available user key in this
dataset. `user_id` must be treated as an optional refinement whose coverage is measured and reported;
GrowthScope must not silently switch user keys between layers. `[ASSUMPTION]` — engineering convention.

---

## 9. Session identification

| Claim | Badge | Evidence |
|---|---|---|
| A session starts when a user views a page/screen with no session currently active, and **by default ends after 30 minutes of user inactivity**; the timeout is configurable (web: Admin → Data Streams → Configure tag settings → *Adjust session timeout*). | `[DOCUMENTED]` | R6 |
| `ga_session_id` is **"automatically generated as the timestamp in seconds when a session starts"**. | `[DOCUMENTED]` | R6 |
| `ga_session_id` is unique **only within a user**, not globally. | `[ASSUMPTION]` (high confidence) | Follows from it being a start-timestamp-in-seconds: two different users can start sessions in the same second. Google's phrasing ("To analyze different sessions outside of Google Analytics, **consider joining the user_id or user_pseudo_id with the session_id**") presupposes this. |
| Therefore the canonical session key is the composite **`(user_pseudo_id, ga_session_id)`**. | `[DOCUMENTED]` (as guidance) | R6, quoted above. R5's queries also always group by `user_pseudo_id` together with `session_id`. |
| `ga_session_number` is the nth session for that user ("a user's third or fifth session"). | `[DOCUMENTED]` | R6 |
| Sessions are estimated (HLL++) in the GA4 UI, but BigQuery computes exact session counts — so "GA4 says N sessions, BigQuery says M sessions" is expected and documented. | `[DOCUMENTED]` | R6 |
| **Session attribution comes from the `session_start` event**, which "carries the information that determines the attribution of the session, such as the gclid, UTM parameters, and referrer"; the model is non-direct last click, with a 90-day key-event lookback by default. | `[DOCUMENTED]` | R6 |
| GA4 sessions **also terminate at midnight** (as in Universal Analytics). | `[UNRESOLVED]` — **not found in the official GA4 documentation reviewed.** | R6's "What counts as a session" section documents only the inactivity timeout: "By default, a session ends or times out after 30 minutes of user inactivity. There is no limit to how long a session can last." No midnight rule is stated. Do not assert a midnight boundary until it is documented or measured. |
| `session_start` is emitted at session start for both web and app; its documented parameters include `client_id`, `ga_session_id`, `ga_session_number`, `ignore_referrer`, `page_location`, `page_referrer`, `page_title`, `traffic_type`. | `[DOCUMENTED]` | R13 |
| A `session_start` event can be missing from `event_params` in some configurations (e.g. filtered by a subproperty), yet GA4 still generates a session id. | `[DOCUMENTED]` | R6 — "Sometimes the session ID isn't associated with the `session_start` event… In these cases, Analytics still generates a session ID." |
| The exact session-scoped acquisition parameter keys present on `session_start` **in this dataset** are unknown and must be enumerated. | `[UNVERIFIED]` | R4 provides the enumeration query. |

**Stitching limitation.** `[ASSUMPTION]` (high confidence): because sessions are keyed by a device-scoped
pseudonymous id, a user who switches device or clears cookies produces two "users" and two disjoint session
histories. No cross-device stitching is possible in this dataset unless `user_id` was populated (R16), and
`[UNRESOLVED]` whether it is populated at all here. Any multi-session metric — repeat purchase rate,
time-to-purchase, cohorts — inherits this limitation and must carry it as a caveat.

---

## 10. E-commerce & revenue fields

### 10.1 Order-level fields (`ecommerce` RECORD)

All rows below are `[DOCUMENTED]` R2 unless noted.

| Field | Type | Documented meaning |
|---|---|---|
| `ecommerce.purchase_revenue` | FLOAT | Purchase revenue **in local currency**, standard unit. *"Populated for purchase event only."* |
| `ecommerce.purchase_revenue_in_usd` | FLOAT | Purchase revenue **in USD**, standard unit. *"Populated for purchase event only."* |
| `ecommerce.refund_value` / `refund_value_in_usd` | FLOAT | Refund amount, local currency / USD. Populated for `refund` events only. |
| `ecommerce.shipping_value` / `shipping_value_in_usd` | FLOAT | Shipping cost, local currency / USD. |
| `ecommerce.tax_value` / `tax_value_in_usd` | FLOAT | Tax amount, local currency / USD. |
| `ecommerce.transaction_id` | STRING | The transaction ID. |
| `ecommerce.total_item_quantity` | INTEGER | Sum of `items.quantity` for the event. |
| `ecommerce.unique_items` | INTEGER | Number of unique items, based on `item_id` + `item_name` + `item_brand`. |

### 10.2 The `purchase_revenue` vs `purchase_revenue_in_usd` question — skeptical treatment

This deserves care because it is easy to get wrong in a portfolio project.

| Claim | Badge | Verdict |
|---|---|---|
| They are **two different fields** with different meanings: `purchase_revenue` is **local currency**, `purchase_revenue_in_usd` is **USD**. | `[DOCUMENTED]` | R2. Confirmed. |
| BigQuery export carries **raw local-currency** values and does **not** apply the property's reporting currency: *"In BigQuery export, the raw transaction values included in the data are in local currency, and aren't based on the reporting currency."* | `[DOCUMENTED]` | R9. Confirmed. |
| Because of the above, summing `purchase_revenue` across events that carry **different** currencies produces a meaningless number, whereas `purchase_revenue_in_usd` is always USD and therefore always safe to sum. | `[ASSUMPTION]` (high confidence) | Direct consequence of R2 + R9. **This is the real currency trap**, and it is about mixing currencies, not about NULLs. |
| "One of `purchase_revenue` / `purchase_revenue_in_usd` may legitimately be NULL depending on the source currency." | **`[UNRESOLVED]` — this claim is NOT supported by the documentation reviewed.** | R2 states both are "populated for purchase event only" with no currency-dependent NULL rule. R9 documents no such rule either. Treat the claim as unproven; the correct statement is the currency-mixing one above. If a NULL-rate asymmetry is observed later, it must be reported as an empirical finding, not as documented behaviour. |
| `purchase_revenue` is NULL on **every non-`purchase` event** (including `refund`). | `[DOCUMENTED]` | R2 — "Populated for purchase event only." |
| Consequence: `SUM(ecommerce.purchase_revenue_in_usd)` over a whole table is safe *by itself* (NULLs are ignored), but any **average** over all rows, or any `COUNT` of non-null revenue, must be restricted to `event_name = 'purchase'` or it will be biased by the vast number of non-purchase events. | `[ASSUMPTION]` (high confidence) | R2. |
| Consequence: refunds are **not** netted out of `purchase_revenue`. Refund value lives in `refund_value*` on `refund` events (R2). Net revenue therefore requires an explicit decision, and GrowthScope must state whether it reports gross purchase revenue or gross-minus-refunds. | `[ASSUMPTION]` | R2. |
| Consequence: revenue is only as reliable as `transaction_id` uniqueness. Google's own guidance uses a *changed* `transaction_id` to prevent deduplication (R15) — i.e. the same underlying order with the same `transaction_id` is deduplicated by GA4, and a duplicate purchase must be measured, not assumed absent. | `[DOCUMENTED]` R15 for the mechanism; `[ASSUMPTION]` for the audit requirement | R15.
| The Google Merchandise Store transacts in **USD**, so `purchase_revenue` and `purchase_revenue_in_usd` are expected to be equal. | `[ASSUMPTION]` — store currency was **not** verified in this environment | Must be tested (§14 Query C) before any code depends on it. GrowthScope should read `purchase_revenue_in_usd` for headline metrics regardless, so the choice does not depend on this assumption. |
| `event_value_in_usd` (top level) is "the currency-converted value (in USD) of the event's **`value` parameter**". | `[DOCUMENTED]` | R2. |
| Therefore `event_value_in_usd` is driven by the `event_params['value']` parameter, **not** by `ecommerce.purchase_revenue`, and the two should not be assumed equal for every event. | `[ASSUMPTION]` (high confidence) | R2 defines them from different sources. Whether they coincide on `purchase` events in this dataset is `[UNVERIFIED]` (§14 Query C). |

### 10.3 Purchase-side mirror inside `event_params`

| Claim | Badge |
|---|---|
| The `purchase` event is sent with top-level ecommerce-style parameters that land in `event_params`: `transaction_id`, `value`, `tax`, `shipping`, `currency`, `coupon` (plus `items[]`). | `[DOCUMENTED]` R14, R15 — the documented `purchase` payload, and R15's parameter→dimension mapping table (`transaction_id`→*Transaction ID*, `shipping`→*Shipping amount*, `tax`→*Tax amount*, `currency`→*Currency*). |
| `payment_type` is documented for **`add_payment_info`**, not for `purchase`. | `[DOCUMENTED]` R14 — `add_payment_info` example carries `payment_type`; the `purchase` example does not. |
| Items inside a `purchase` event are stored in the repeated `items` array, **not** as `event_params` keys — except for custom item parameters, which go to `items[].item_params`. | `[DOCUMENTED]` R2 ("predefined item parameters… are exported as explicit fields"), R14 |
| Items may **also** appear as legacy event parameters in old app SDK exports; R2 documents that on the new schema "item data will no longer be available in standard event parameters". That migration note is framed around Android/iOS SDK versions, so its applicability to a 2020 **web** export is `[UNRESOLVED]`. | `[DOCUMENTED]` for the rule (R2); `[UNRESOLVED]` for this dataset |
| **Risk to state explicitly:** reading revenue from `event_params['value']` *and* from `ecommerce.purchase_revenue*` in the same metric double-counts. Pick one basis, document it, and test for divergence. | `[ASSUMPTION]` (high confidence) |

### 10.4 Item-level fields (`items` REPEATED RECORD)

All definitions `[DOCUMENTED]` R2; parameter names cross-checked against R14.

| Field | Type | Documented meaning |
|---|---|---|
| `items.item_id` | STRING | Item ID (SKU). One of `item_id` / `item_name` is required by R14. |
| `items.item_name` | STRING | Item name. |
| `items.item_brand` | STRING | Item brand. |
| `items.item_variant` | STRING | Item variant. |
| `items.item_category` | STRING | Item category. |
| `items.item_category2` … `items.item_category5` | STRING | Sub-categories (4 additional levels). |
| `items.price_in_usd` | FLOAT | Unit price, USD, standard unit. |
| `items.price` | FLOAT | Unit price, local currency. |
| `items.quantity` | INTEGER | Quantity. **Defaults to 1 if not specified** (R2, R14). |
| `items.item_revenue_in_usd` | FLOAT | `price_in_usd * quantity`. **Populated for purchase events only.** |
| `items.item_revenue` | FLOAT | `price * quantity`. **Populated for purchase events only.** |
| `items.item_refund_in_usd` | FLOAT | `price_in_usd * quantity`. **Populated for refund events only.** |
| `items.item_refund` | FLOAT | `price * quantity`. **Populated for refund events only.** |
| `items.coupon` | STRING | Coupon code applied to this item. |
| `items.affiliation` | STRING | Supplying company / brick-and-mortar location. |
| `items.location_id` | STRING | Location associated with the item (Google Place ID style value; R15 shows a real example). |
| `items.item_list_id` | STRING | ID of the list the item was presented in. |
| `items.item_list_name` | STRING | Name of that list. |
| `items.item_list_index` | STRING | Position of the item in a list. **Documented type is STRING**, so it must be cast before numeric ordering. |
| `items.promotion_id` | STRING | Promotion ID. |
| `items.promotion_name` | STRING | Promotion name. |
| `items.creative_name` | STRING | Creative name used in a promotional spot. |
| `items.creative_slot` | STRING | Creative slot name. |
| `items.item_params` | REPEATED RECORD | Custom item-scoped parameters only (`key`, `value.{string,int,double,float}_value`). |
| `discount` | — | Present in GA4 ecommerce payloads (R14) and in R15's parameter→dimension table (*Item discount amount*), but **there is no `items.discount` column in R2's item list**. `[UNRESOLVED]` — where `discount` lands in the export must be verified before it is used. |
| `index` | — | Sent as `index` in payloads (R14) and mapped to *Item list position* (R15); R2 exposes `items.item_list_index`. `[ASSUMPTION]` that these are the same value. |

---

## 11. Acquisition, device and geographic attributes

### 11.1 First-user vs session scope — this distinction is the whole point

| Field / dimension | Scope | Documented meaning | Badge |
|---|---|---|---|
| `traffic_source.{name, medium, source}` | **USER (first acquisition)** | "contains information about the traffic source that **first acquired the user**. This record is not populated in intraday tables. **Note:** The `traffic_source` values do not change if the user interacts with subsequent campaigns after installation." | `[DOCUMENTED]` R2 |
| First-user dimensions ("First user source / medium / campaign") | **USER** | "show you where your **new users** are coming from… The value assigned to each user-scoped dimension remains the same as users return." Uses paid-and-organic last click and is *not* affected by attribution-model changes. | `[DOCUMENTED]` R8 |
| Session dimensions ("Session source / medium…") | **SESSION** | "show you where both new and returning users are coming from **when they start new sessions**… New values are assigned to session-scoped dimensions each time users return." | `[DOCUMENTED]` R8 |
| Event-scoped *Source* / *Medium* | **EVENT** | "For **non-key events** the source and medium are `(not set)`." Event-scoped dimensions follow the property's attribution model (default: data-driven). | `[DOCUMENTED]` R8 |
| `session_traffic_source_last_click` | **SESSION** | "last-click attributed session traffic source data across Google ads and manual contexts, where available." | `[DOCUMENTED]` as current schema (R2); presence here `[UNRESOLVED]` |
| `collected_traffic_source` | **EVENT (as collected)** | "the traffic source data that was present within the events that were collected." Holds `manual_*` (UTM-derived), plus `gclid`, `dclid`, `srsltid`. | `[DOCUMENTED]` as current schema (R2); presence here `[UNRESOLVED]` |
| `session_start` event | carries **session** attribution input | "carries the information that determines the attribution of the session, such as the gclid, UTM parameters, and referrer." | `[DOCUMENTED]` R6 |

> ### ⚠️ First-user acquisition is **not** session attribution
> `[DOCUMENTED]` (R2 + R8). `traffic_source` on an event row describes how that **user was first acquired**,
> frozen forever, and is identical on every row belonging to that user. It is **not** the channel of the
> current session. R8's worked example makes the difference concrete: the same user has *First user
> source/medium* = `google / organic` while their four sessions are attributed to
> `google / organic`, `email / newsletter`, `google / cpc` and `partner / affiliate`.
>
> **Consequence.** Any GrowthScope screen labelled "channel performance" must state which of the two it
> shows. Attributing *purchases* to `traffic_source.source` attributes the sale to the user-acquisition
> channel — a defensible "first-touch by user" metric, but a different number from GA4's Traffic
> Acquisition report, and it must be labelled accordingly. `[ASSUMPTION]` — engineering convention derived
> from the documented scopes.
>
> A second documented nuance to carry: *"Sessions initiated by direct entrance are attributed to the UTM
> values for that user."* `[DOCUMENTED]` R8. Direct sessions are therefore not simply "Direct".

### 11.2 Default channel grouping

| Claim | Badge | Evidence |
|---|---|---|
| Default channel groups **cannot be edited**; three scoped variants exist — *Default channel group* (event scope, property attribution model), *Session default channel group* (session scope, paid-and-organic last click), *First user default channel group* (user scope, paid-and-organic last click). | `[DOCUMENTED]` | R7 |
| The full channel set is documented (Affiliates, AI Assistant, Audio, Cross-network, Direct, Display, Email, Mobile Push Notifications, Organic Search, Organic Shopping, Organic Social, Organic Video, Paid Other, Paid Search, Paid Shopping, Paid Social, Paid Video, Referral, SMS). | `[DOCUMENTED]` | R7 |
| Channel rules are **not case sensitive** and are defined over source/medium/campaign patterns (e.g. `Display` when medium ∈ {display, banner, expandable, interstitial, cpm}; `Paid Search` when source ∈ search-site list AND medium matches `^.*cp.*|ppc|retargeting|paid.*$`). | `[DOCUMENTED]` | R7 |
| `Unassigned` is used when no rule matches; `(other)` is used for aggregated rows due to cardinality limits. | `[DOCUMENTED]` | R7 |
| Channel definitions may **evolve over time**, and data prior to **2022-06-15** may be inconsistent across integrations (e.g. Organic Shopping misidentified as Organic Search). | `[DOCUMENTED]` | R7 — directly relevant, because this dataset is from 2020–2021 and predates that date. |
| Because of the 2022-06-15 caveat, re-deriving default channel groups in SQL for a 2020 dataset is **not** guaranteed to reproduce what GA4 would report today. | `[ASSUMPTION]` (high confidence) | R7 |
| The default channel group is **not** a column in the event export. It must be derived in SQL from source/medium/campaign, or obtained from a reporting surface. | `[ASSUMPTION]` (high confidence) | R2's column list contains no channel-group field. |
| Google publishes a downloadable spreadsheet of the GA4 default-channel-group source/category lists. | `[DOCUMENTED]` | R7 — direct `storage.googleapis.com` link on the page. |

### 11.3 Device and geographic attributes

| Claim | Badge |
|---|---|
| `device.category` is one of `mobile`, `tablet`, `desktop`. | `[DOCUMENTED]` R2 |
| Web-specific fields live under `device.web_info`: `browser`, `browser_version`, `hostname`. | `[DOCUMENTED]` R2 |
| `device.language`, `device.operating_system`, `device.operating_system_version`, `device.time_zone_offset_seconds` are available. | `[DOCUMENTED]` R2 |
| `geo.{continent, sub_continent, country, region, metro, city}` are derived from IP address. | `[DOCUMENTED]` R2 |
| A small share of rows has missing/blank `device` values. | `[UNVERIFIED]` — Google does not document a missing-device rate for this dataset, and it cannot be measured here. It is plausible (the README anticipates a missing-data report) but **must not be quoted as a number**. See §14 Query E. |
| IP-derived geo is an approximation (VPNs, proxies, mobile carrier routing) and is not a verified user location. | `[ASSUMPTION]` (standard analytics caveat; R2 only says "based on IP address") |

### 11.4 A caution about machine-generated Google-hosted catalogue files

The `GoogleCloudPlatform/knowledge-catalog` files (N6) are hosted under a Google GitHub organisation, which
makes them look authoritative. They are **not**:

- Both files carry `generated.by: reference_agent/gemini-3.5-flash` metadata — they are LLM-generated summaries. `[DOCUMENTED]` (visible in the files' YAML front matter).
- The dataset file states the range as "November 1, 2020, to **January 1, 2021**", contradicting both the primary documentation (R1) and its own sibling table file. `[DOCUMENTED]` (observable contradiction) / `[UNRESOLVED]` (which is right — R1 wins).
- The table file lists `user_properties.key` as **INTEGER** and `privacy_info.analytics_storage` as **INTEGER**, whereas R2 defines both as STRING. `[DOCUMENTED]` (contradiction).
- The table file lists `event_dimensions.hostname` and a populated `user_ltv`, which are not part of R2's documented event schema for web properties (`user_ltv` is defined in R2, but its presence per shard here is unproven). `[UNRESOLVED]`.

**Rule:** field-level truth comes from R2 plus a live `INFORMATION_SCHEMA` read — never from a
Google-hosted generated summary. `[ASSUMPTION]` — engineering convention.

---

## 12. Known limitations of this dataset

| # | Limitation | Badge | Impact on GrowthScope |
|---|---|---|---|
| L1 | **Obfuscated data with placeholder values** — "Certain fields will contain placeholder values including `<Other>`, `NULL`, and `''`." | `[DOCUMENTED]` R1 | Every dimension breakdown needs a "unknown/placeholder" category; proportions must be reported, not filtered away. |
| L2 | **Limited internal consistency** — "Due to obfuscation, internal consistency of the dataset might be somewhat limited." | `[DOCUMENTED]` R1 | Item prices, revenue and quantity may not reconcile perfectly. Reconciliation tests must have a stated tolerance and the residual must be reported. |
| L3 | It is a **sample**, not the complete export. | `[DOCUMENTED]` R1 ("contains a sample of obfuscated…") | Absolute volumes are illustrative; the project must not present them as the store's real business results. |
| L4 | **Not comparable to the GA4 demo account** — the underlying data differs. | `[DOCUMENTED]` R1 | Never mix the two sources; never cite demo-account figures as validation. |
| L5 | **`user_id` is expected to be empty for nearly all rows.** | `[ASSUMPTION]` (high confidence) / `[UNVERIFIED]` here | No cross-device stitching; cohorts are device-cohorts. Measure and publish the non-null share. |
| L6 | **No advertising cost or spend data.** The documented event-export schema (R2) contains no cost/spend/impression-share column. | `[ASSUMPTION]` (high confidence), inferred from the documented schema; `[UNVERIFIED]` as an exhaustive check | **CAC, ROAS, ROMI and ad profit are impossible.** GrowthScope must not approximate them. This is already an explicit constraint in the README. |
| L7 | **`traffic_source` is first-user scope only, and static per user.** | `[DOCUMENTED]` R2, R8 | Cannot be used as session or event attribution (see §11.1). |
| L8 | **Session-scoped acquisition structures may not exist in these shards** (`session_traffic_source_last_click`; also `collected_traffic_source`). | `[ASSUMPTION]` (high confidence, structural) — introduced 2023/2024 per N1–N3; per-day tables are not retro-filled | Practical session attribution must be reconstructed from `session_start`'s `event_params` (source/medium/campaign/referrer/gclid). That reconstruction is the honest fallback and must be labelled as reconstructed. |
| L9 | **Date window is 92 days in a single season.** | `[DOCUMENTED]` R1 + `[ASSUMPTION]` (92-day arithmetic) | No year-over-year, no full-year seasonality, weak long-run retention claims. Retention can only be stated over ≤ 3 months of observation. |
| L10 | **Cookie/device fragmentation** (400-day Chrome / 7-day Safari caps; cleared cookies; new devices). | `[DOCUMENTED]` R10 + R2 | "Returning users" is under-counted; new-user counts are over-counted. |
| L11 | **BigQuery export is Device-ID based**, and GA4-vs-BigQuery event counts legitimately differ by 2–5%. | `[DOCUMENTED]` R11 | Do not treat a mismatch with the GA4 UI as a bug. Comparisons must be documented as definitionally different. |
| L12 | **No `batch_page_id` / `batch_ordering_id` / `batch_event_index`.** | `[DOCUMENTED]` R4 | The documented "sequence of pageviews" ordering recipe does not apply here. Event ordering must use `event_timestamp`, with `event_previous_timestamp` as a secondary signal, and ties broken explicitly. Same-second ties are a documented reality (R2: "Multiple events can share the same timestamp if sent in the same request"). |
| L13 | **The GA4 demo account cannot be used as a cross-check**: it blocks export functionality, the device-ID dimension, and the Analytics Data API. | `[DOCUMENTED]` R12 | There is no second, independent data source to validate against. Validation must be internal (capital conservation, funnel monotonicity, reconciliation). |
| L14 | **Docs describe today's schema, not the 2020 schema**; only three columns are officially confirmed absent. | `[DOCUMENTED]` (the doc-vs-data gap) R2/R4 | No column may be assumed present. Enumerate first (§14 Query B), code second. |

---

## 13. Non-BigQuery exports and mirrors

**Question asked:** does an officially sanctioned, citable non-BigQuery export of this dataset exist
(CSV, Kaggle, or Google-hosted download)?

| Finding | Badge |
|---|---|
| **No officially sanctioned non-BigQuery export was found.** The only access paths Google documents for this dataset are BigQuery-based: the Cloud console query UI (R1), the general public-dataset access routes — Cloud console, `bq` CLI, REST API, client libraries (R17) — and Connected Sheets, which pulls BigQuery results into Google Sheets (offered under "Next steps" on R1). Connected Sheets is a sanctioned *access surface* but it is still BigQuery underneath; it is not a downloadable distribution of the dataset. | `[UNRESOLVED]` — a negative finding from desk research, not a proof. Google does not document a CSV/Parquet/archive download, but absence of documentation is not documentation of absence. |
| The dataset is **not** the same as the GA4 demo account data, so demo-account exports (which R12 documents as unavailable anyway) are not a substitute. | `[DOCUMENTED]` R1, R12 |
| The public dataset programme's **terms** are not stated on R1. R1's own licence footer (CC-BY-4.0 for page content, Apache-2.0 for code samples) covers *the documentation page*, not the dataset. | `[UNRESOLVED]` — no dataset-specific licence statement was found in the pages reviewed. Do not assert a dataset licence. |
| **Unofficial derivative #1 — Observable "Google Merchandise Sales Data"** (N5), `https://observablehq.com/@observablehq/google-merchandise-sales-data`. Published by Observable (the company behind Observable notebooks, D3 and Plot). Verified by reading the notebook's source: it offers **CSV and Apache Parquet** attachments (`items.csv`, `events@1.csv`, `users.csv`, plus `.parquet` counterparts) and a DuckDB client. | `[DOCUMENTED]` as a real artefact (notebook source read at `https://api.observablehq.com/@observablehq/google-merchandise-sales-data.js`) — **UNOFFICIAL relative to Google** |
| **Critical caveat on #1:** it is a **reshaped, curated subset**, not a copy of the export. The notebook describes three tables (`items`, `events`, `users`) and states the `events` table "captures three event types (`type`): `add_to_cart`, `begin_checkout`, and `purchase`". It therefore drops `page_view`, `session_start`, `view_item`, `view_item_list` and everything else. The `users` table carries a pre-computed `ltv` and first-touch date described as values "supplied by the original dataset as calculated values that fall outside the range of the published data". | `[DOCUMENTED]` (read from the notebook source) |
| **Verdict on #1:** usable as a *convenience sample for teaching/EDA* and as a sanity check for item-level shapes. **Not usable** to verify this dataset's schema, its date coverage, or any session/funnel metric — three of the four funnel steps do not exist in it. Do not commit it as project data; do not cite it as authoritative. | `[ASSUMPTION]` (assessment) |
| **Unofficial derivative #2 — Kaggle "Google Merchandise Store" datasets.** A Kaggle search surfaced e.g. `adityajha1504/google-merchandise-adding-to-cart-prediction`, described as "obfuscated Google Analytics data on each visitor session" for the Google Merchandise Store. The Kaggle page could not be loaded from this environment, so its contents were not inspected. | `[UNRESOLVED]` / `[UNVERIFIED]` |
| **Warning on #2:** the long-standing Kaggle "Google Merchandise Store" datasets are derived from the **Universal Analytics / GAv2-era** store data (the classic 2016–2018 session-level set), not from `ga4_obfuscated_sample_ecommerce`. Their columns (`channelGrouping`, `hits`, `totals`, `fullVisitorId`) are UA-shaped and incompatible with the GA4 event schema. Any Kaggle mirror must be verified to contain `event_name` / `user_pseudo_id` / `event_params` before it is treated as this dataset. | `[ASSUMPTION]` (high confidence, based on well-known dataset lineage) — must be verified if ever used |
| **Google-hosted but unreliable #3 — `GoogleCloudPlatform/knowledge-catalog` OKF bundle** (N6). | See §11.4. |
| **Other Google-hosted datasets that are *not* this dataset**: the sibling `app-*` sample (Firebase/app), the `samples.*` tables under `bigquery-public-data:samples` (R17). | `[DOCUMENTED]` R1 (links to a gaming/app sample), R17 |

**Action for the project.** Do not depend on any mirror. Route all data access through BigQuery. If a
mirror is ever used (e.g. for a CI fixture), it must be committed only as a **small aggregated** artefact,
labelled "derived from the unofficial Observable subset", and never presented as the official dataset —
which matches the README's existing commitment ("no raw events; only small aggregated demo data").

---

## 14. How to verify these findings yourself

Requires a Google Cloud project with the BigQuery API enabled; BigQuery Sandbox is sufficient (R1, R17).
Public datasets are in the `US` multi-region (R17).

### Console steps

1. Open the dataset deep-link from R1 — `https://console.cloud.google.com/bigquery?p=bigquery-public-data&d=ga4_obfuscated_sample_ecommerce&t=events_20210131&page=table` — or navigate **Explorer → `bigquery-public-data` → `ga4_obfuscated_sample_ecommerce`**.
2. In **Explorer**, expand the dataset and read the shard list. Record the **first and last `events_YYYYMMDD`** names — this is the only authoritative confirmation of the coverage endpoints.
3. Click any shard → **Schema** tab. This resolves every `[UNVERIFIED]` column in §5, including whether `collected_traffic_source`, `session_traffic_source_last_click`, `privacy_info`, `is_active_user` and `user_ltv` exist in that shard.
4. Compare the **Schema** of the first shard with the last shard. Differences prove that the schema is not uniform across the window.
5. Check the **Details** tab of a shard for *Number of rows* and *Last modified*.

Record findings in `docs/data_limitations.md` (or a Sprint 02 data-profile note) and downgrade/upgrade the badges in this document accordingly.

### Minimal SQL snippets

**Query A — confirm the shard inventory, per-table row counts and sizes (metadata read, no table scan).**

```sql
SELECT
  table_id,
  row_count,
  ROUND(size_bytes / 1024 / 1024, 1) AS size_mb
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.__TABLES__`
ORDER BY table_id;
```

Confirms or refutes: the first/last shard (§3), the date continuity (missing days), and that the shards hold rows.

**Query B — resolve the schema question per shard (wildcard tables cannot be read from `INFORMATION_SCHEMA.COLUMNS` directly, so name the shards explicitly).**

```sql
SELECT
  table_name,
  column_name,
  data_type,
  is_nullable
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.INFORMATION_SCHEMA.COLUMNS`
WHERE table_name IN ('events_20201101', 'events_20210131')
ORDER BY table_name, ordinal_position;
```

This is the single highest-value query in the project: it settles every `[UNVERIFIED]` and
`[ASSUMPTION]` column-presence statement in §5. Run it **before** writing any staging SQL.

**Query C — settle the revenue question (§10.2).**

```sql
SELECT
  COUNT(*)                                                  AS purchase_rows,
  COUNTIF(ecommerce.purchase_revenue IS NULL)               AS revenue_null,
  COUNTIF(ecommerce.purchase_revenue_in_usd IS NULL)        AS revenue_usd_null,
  COUNTIF(ecommerce.purchase_revenue IS NOT NULL
          AND ecommerce.purchase_revenue_in_usd IS NOT NULL
          AND ROUND(ecommerce.purchase_revenue, 2)
              <> ROUND(ecommerce.purchase_revenue_in_usd, 2)) AS differing_rows,
  ROUND(SUM(ecommerce.purchase_revenue_in_usd), 2)          AS total_revenue_usd
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
WHERE _TABLE_SUFFIX BETWEEN '20201101' AND '20210131'
  AND event_name = 'purchase';
```

`revenue_null = 0` and `differing_rows = 0` would confirm the USD assumption in §10.2; any non-zero
`revenue_null` or `differing_rows` would show that the local/USD distinction is materially observable here.
Do **not** compute this from `event_params['value']` in the same query — that would conflate bases (§10.3).

**Query D — confirm the funnel event inventory and the session key (§5.1, §9).**

```sql
SELECT
  event_name,
  COUNT(*) AS events,
  COUNT(DISTINCT user_pseudo_id) AS users,
  COUNTIF(
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') IS NULL
  ) AS events_without_session_id
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
WHERE _TABLE_SUFFIX BETWEEN '20201101' AND '20210131'
GROUP BY event_name
ORDER BY events DESC;
```

This settles which funnel steps actually exist (§5.1) and quantifies the "events not attributable to a
session" share that §6.2 says must be measured rather than dropped.

**Query E — acquisition and device coverage (§11), including the first-user vs session question.**

```sql
SELECT
  traffic_source.source AS first_user_source,
  traffic_source.medium AS first_user_medium,
  device.category       AS device_category,
  COUNT(DISTINCT user_pseudo_id) AS users,
  COUNT(DISTINCT CONCAT(user_pseudo_id, '.',
    CAST((SELECT value.int_value FROM UNNEST(event_params)
          WHERE key = 'ga_session_id') AS STRING))) AS sessions
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
WHERE _TABLE_SUFFIX BETWEEN '20201101' AND '20210131'
  AND event_name = 'session_start'
GROUP BY 1, 2, 3
ORDER BY sessions DESC
LIMIT 50;
```

Note what this query is *doing*: it groups sessions by **first-user** source/medium, because that is all
`traffic_source` can express (§11.1). If session-level attribution is needed instead, it must come from
`session_start`'s own `event_params` (or `session_traffic_source_last_click`, if Query B shows it exists).
`COUNTIF(device.category IS NULL)` added to this query answers the missing-device question in §11.3.

---

## 15. Open questions & risks

| # | Question / risk | Status | Why it matters |
|---|---|---|---|
| Q1 | Which columns actually exist in the 2020-era shards, and are the first and last shards identical in schema? | `[UNRESOLVED]` → §14 Query B | Every staging model depends on it. |
| Q2 | Are `collected_traffic_source` and `session_traffic_source_last_click` present, and are they NULL where present? | `[UNRESOLVED]` → §14 Query B | Determines whether real session attribution is available or must be reconstructed from `session_start` params. |
| Q3 | Does `is_active_user` exist, and does `user_ltv` exist (R2 defines it; its presence here is unproven)? | `[UNRESOLVED]` → §14 Query B | Affects active-user and LTV-style metrics; a hallucinated field would break the pipeline. |
| Q4 | Is `purchase_revenue` always equal to `purchase_revenue_in_usd` in this dataset? | `[UNRESOLVED]` → §14 Query C | Decides whether the local-currency trap is theoretical or live. |
| Q5 | Which funnel steps actually appear (`view_item`, `begin_checkout`), and how many sessions lack a `ga_session_id`? | `[UNRESOLVED]` → §14 Query D | The funnel cannot be designed against assumed event names. |
| Q6 | How large is the placeholder burden (`<Other>`, `NULL`, `''`) per critical dimension, and what share of rows has a missing `device`? | `[UNRESOLVED]` → §14 Query E | Determines whether channel/device breakdowns are publishable or need a confidence flag. |
| Q7 | Does GA4 terminate a session at midnight? | `[UNRESOLVED]` — not stated in R6 | Changes session counts and therefore conversion rates. Measure empirically: find `(user_pseudo_id, ga_session_id)` pairs whose events straddle midnight. |
| Q8 | Where does the `discount` parameter land in the export (§10.4)? | `[UNRESOLVED]` | Affects net-revenue and promotion analysis. |
| Q9 | Is `event_value_in_usd` equal to `ecommerce.purchase_revenue_in_usd` on purchase events? | `[UNRESOLVED]` | Decides which field is the single revenue source of truth. |
| Q10 | What are the dataset's licence/attribution terms? | `[UNRESOLVED]` | Needed for the public repo and any published demo artefact. |
| Q11 | Do refund events exist in this dataset, and how large is refund value relative to purchases? | `[UNRESOLVED]` | Decides whether revenue must be reported net or gross (§10.2). |
| Q12 | **Risk:** the environment has no BigQuery access at all, so Sprint 02's data profile cannot be produced here. | `[BLOCKED — NO BIGQUERY ACCESS]` | The whole analysis depends on a credentialed environment being available. |

---

## 16. What Sprint 02 must resolve

Ordered by cost-of-being-wrong. Each item is a precondition for the layer it precedes.

1. **Establish BigQuery access** (project + ADC, Sandbox is enough per R1/R17) and record the exact
   verification command in the repo. Without this, nothing below is possible. — unblocks Q12.
2. **Run §14 Query A.** Freeze the exact shard list and per-shard row counts into `docs/data_limitations.md`. Resolve Q1's first half.
3. **Run §14 Query B, and diff the first vs last shard schema.** Publish the resulting column inventory
   as the canonical schema record for the project and update every `[UNVERIFIED]`/`[ASSUMPTION]` badge in
   this document. Resolve Q1 (second half), Q2, Q3.
4. **Run §14 Query D.** Freeze the real event-name inventory and the "events without `ga_session_id`" share
   before writing any session SQL. Resolve Q5. Also settle Q7 empirically (midnight straddling).
5. **Run §14 Query C.** Choose and document one revenue basis (`purchase_revenue_in_usd` recommended) and
   one revenue layer (order-level `ecommerce.*` **or** item-level `items.*`, never both). Resolve Q4, Q9, Q11.
6. **Run §14 Query E and a placeholder-profile query.** Quantify `<Other>`/`NULL`/`''` and missing-device
   shares per critical dimension. Resolve Q6. Produce the "Data Quality Monitor" inputs.
7. **Decide and document the attribution contract** before any acquisition screen exists: first-user
   attribution (available today from `traffic_source`) vs reconstructed session attribution (from
   `session_start` params). Resolve Q2's consequence. Label every screen accordingly.
8. **Document the dataset licence/attribution terms** (Q10) before publishing dashboards or demo artefacts.
9. **Write the canonical ordered-event-ordering rule** using `event_timestamp` (and
   `event_previous_timestamp` where useful), with an explicit tie-break, since `batch_*` columns are
   documented absent (R4, L12).
10. **Do not start funnel metrics until items 1–5 are done.** Any funnel built on an assumed event name or
    an assumed session key is an unverified metric, and this project's stated standard is that every metric
    ships with a reliability note (README, "Limitations and honest analytics").

---

*Independent portfolio project. Not affiliated with, endorsed by, or sponsored by Google. All Google
documentation is quoted for technical accuracy and attributed by URL in §1.*
