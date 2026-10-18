# GrowthScope — Data Dictionary

Field-level reference for the GA4 event export, scoped to what GrowthScope analyses need.

- **Source of truth for structure:** the official [BigQuery Export schema](https://support.google.com/analytics/answer/7029846) and the [GA4 e-commerce sample dataset](https://developers.google.com/analytics/bigquery/web-ecommerce-demo-dataset).
- **Dataset:** `bigquery-public-data.ga4_obfuscated_sample_ecommerce` — obfuscated Google Merchandise Store export, **2020-11-01 → 2021-01-31**.
- **Environment:** no BigQuery credentials were available during Sprint 01, so **no field below has been verified against the live tables**. This document describes the documented export schema; the sample's actual table list, populated fields and value distributions must be confirmed in Sprint 02 with the queries in `sql/exploration/`.

## Verification legend

| Tag | Meaning |
|---|---|
| `[DOCUMENTED]` | Stated on an official Google page (URL given in the row or section). |
| `[UNVERIFIED — needs BigQuery]` | Could not be checked against the live dataset in this environment; must be confirmed in Sprint 02. |
| `[ASSUMPTION]` | Engineering assumption made for analysis; not (yet) backed by a reference or observation. |

> [!NOTE]
> **Example values are illustrative shapes, not real values.** The `Example` column uses placeholder syntax (`<string>`, `20201101`, `1.2345`) to show the *shape* a value takes. It never shows data read from the dataset.

> [!WARNING]
> The dataset is **obfuscated and partially adjusted by Google**. Google states: *"Certain fields will contain placeholder values including `<Other>`, `NULL`, and `''`. Due to obfuscation, internal consistency of the dataset might be somewhat limited."* ([source](https://developers.google.com/analytics/bigquery/web-ecommerce-demo-dataset)). Treat all values as structure-illustrative, **not business truth**.

---

## 1. Top-level fields

One row per top-level column. Fields whose type is `RECORD` have their children listed in section 1.1 or in their own sub-tables below. Modes other than `REPEATED` are `NULLABLE` in the export schema.

| Field path | Type | Mode | Description `[DOCUMENTED]` | Example (illustrative shape) | Used for | Verification |
|---|---|---|---|---|---|---|
| `batch_event_index` | INTEGER | NULLABLE | Sequential order of the event within its upload batch. | `4` | Tie-breaking diagnostics; event ordering sanity checks | `[DOCUMENTED]` |
| `batch_ordering_id` | INTEGER | NULLABLE | Counter incremented per network request from a page. | `12` | Diagnosing batching and ordering; secondary tie-breaker | `[DOCUMENTED]` |
| `batch_page_id` | INTEGER | NULLABLE | Sequential page number within an engagement. | `3` | Batching diagnostics | `[DOCUMENTED]` |
| `event_date` | STRING | NULLABLE | Date the event was logged, `YYYYMMDD` in the property timezone. | `'20201101'` | Day grain; `_TABLE_SUFFIX` filtering; daily KPIs | `[DOCUMENTED]` |
| `event_timestamp` | INTEGER | NULLABLE | Time in **microseconds, UTC** the event was received by GA. Multiple events may share a timestamp. | `1604197000000000` | Session ordering; funnel windows; latency | `[DOCUMENTED]` |
| `event_previous_timestamp` | INTEGER | NULLABLE | Time in microseconds (UTC) of the user's previous event. | `1604196000000000` | Time-between-events diagnostics | `[DOCUMENTED]` |
| `event_name` | STRING | NULLABLE | The event name (e.g. `page_view`, `view_item`). | `'view_item'` | Event catalog; funnel steps | `[DOCUMENTED]` |
| `event_value_in_usd` | FLOAT | NULLABLE | Currency-converted value (USD) of the event's `value` parameter. | `49.99` | Value-based diagnostics; revenue cross-checks | `[DOCUMENTED]` |
| `event_bundle_sequence_id` | INTEGER | NULLABLE | Sequential ID of the uploaded bundle. | `10` | Batching diagnostics | `[DOCUMENTED]` |
| `event_server_timestamp_offset` | INTEGER | NULLABLE | Offset in microseconds between collection and upload time. | `123456` | Collection-latency diagnostics | `[DOCUMENTED]` |
| `is_active_user` | BOOLEAN | NULLABLE | Whether the user was active at any point in the calendar day; populated only in daily tables. | `TRUE` | Daily active-user definition; coverage checks | `[DOCUMENTED]` |
| `user_id` | STRING | NULLABLE | The unique ID assigned to a user (only when you set one). | `<string id>` | Logged-in identity when available | `[DOCUMENTED]`; population in sample `[UNVERIFIED — needs BigQuery]` (likely mostly empty) |
| `user_pseudo_id` | STRING | NULLABLE | Pseudonymous per-device/browser identifier assigned at first visit. | `<string id>` | User counting; **part of the session key** | `[DOCUMENTED]` |
| `user_first_touch_timestamp` | INTEGER | NULLABLE | Time in **microseconds** when the user first opened the app / visited the site. | `1602000000000000` | First-touch recency; new vs returning approximations | `[DOCUMENTED]` |
| `privacy_info` | RECORD | NULLABLE | Consent-mode state: `analytics_storage`, `ads_storage`, `uses_transient_token` (each STRING: `Yes`/`No`/`Unset`). | `analytics_storage = 'Yes'` | Consent-state audit and segmentation | `[DOCUMENTED]`; presence in sample `[UNVERIFIED — needs BigQuery]` |
| `user_properties` | RECORD | REPEATED | User-scoped key/value pairs: `key`, `value.{string_value,int_value,double_value,float_value,set_timestamp_micros}`. | `key='language', string_value='en'` | Custom user attributes (none expected for this store) | `[DOCUMENTED]`; contents `[UNVERIFIED — needs BigQuery]` |
| `user_ltv` | RECORD | NULLABLE | Lifetime value: `revenue` (FLOAT), `currency` (STRING). Not populated in intraday tables. | `revenue = 123.45` | Historical LTV reference — diagnostic only, lifetime scope, not window-scoped | `[DOCUMENTED]`; population `[UNVERIFIED — needs BigQuery]` |
| `device` | RECORD | NULLABLE | Device context; see section 1.1. | `category = 'mobile'` | Device segmentation; mobile vs desktop funnel gaps | `[DOCUMENTED]`; values `[UNVERIFIED — needs BigQuery]` |
| `geo` | RECORD | NULLABLE | Geography from IP: `continent`, `sub_continent`, `country`, `region`, `metro`, `city` (all STRING). | `country = 'United States'` | Geography segmentation | `[DOCUMENTED]`; values `[UNVERIFIED — needs BigQuery]` |
| `app_info` | RECORD | NULLABLE | App metadata: `id`, `firebase_app_id`, `install_source`, `version`. | `id = '<app package>'` | App-stream segmentation | `[DOCUMENTED]`; **not expected for this web property** `[UNVERIFIED — needs BigQuery]` |
| `collected_traffic_source` | RECORD | NULLABLE | Traffic-source data collected with the event: `manual_campaign_id`, `manual_campaign_name`, `manual_source`, `manual_medium`, `manual_term`, `manual_content`, `manual_creative_format`, `manual_marketing_tactic`, `manual_source_platform` (STRING), `gclid`, `dclid`, `srsltid` (STRING). | `manual_medium = 'cpc'` | Session-level landing context (campaign, gclid) | `[DOCUMENTED]`; population, and whether `srsltid`/`dclid` exist in this 2020-21 export `[UNVERIFIED — needs BigQuery]` |
| `session_traffic_source_last_click` | RECORD | NULLABLE | Last-click attributed session traffic source, grouped by `manual_campaign`, `google_ads_campaign`, `cross_channel_campaign`, `sa360_campaign`, `dv360_campaign`, `cm360_campaign` sub-records. | `google_ads_campaign.campaign_name = '<string>'` | Last-click session attribution | `[DOCUMENTED]`; **likely absent** — field docs are newer than this 2020-21 export `[UNVERIFIED — needs BigQuery]` |
| `traffic_source` | RECORD | NULLABLE | **First-user acquisition**: `name`, `medium`, `source` (all STRING). Does not change after acquisition. | `source = 'google'` | First-user acquisition reporting (never mixed with session attribution) | `[DOCUMENTED]`; values `[UNVERIFIED — needs BigQuery]` |
| `stream_id` | STRING | NULLABLE | Numeric ID of the data stream the event came from (typed STRING). | `'1234567890'` | Multi-stream segmentation | `[DOCUMENTED]`; value `[UNVERIFIED — needs BigQuery]` |
| `platform` | STRING | NULLABLE | Data-stream platform: `Web`, `IOS` or `Android`. | `'Web'` | Stream filtering; sanity checks | `[DOCUMENTED]`; value `[UNVERIFIED — needs BigQuery]` |
| `ecommerce` | RECORD | NULLABLE | Transaction-level e-commerce data; see section 1.2. | `transaction_id = '<string>'` | Order counts; revenue; dedup key | `[DOCUMENTED]`; population `[UNVERIFIED — needs BigQuery]` |
| `items` | RECORD | REPEATED | Item-level e-commerce data; see section 1.3. | `item_name = '<string>'` | Product analytics; basket size | `[DOCUMENTED]`; population `[UNVERIFIED — needs BigQuery]` |
| `event_params` | RECORD | REPEATED | Parameter key/value bag; see section 1.4 and the key reference in section 2. | `key='page_location'` | Session reconstruction, campaign context, engagement | `[DOCUMENTED]`; observed keys `[UNVERIFIED — needs BigQuery]` |
| `publisher` | RECORD | REPEATED | AdMob publisher data ("Early access only"). | — | **Not applicable** to this web dataset | `[DOCUMENTED]` |

### 1.1 Other RECORD children (quick reference)

| Parent | Children (type) |
|---|---|
| `device` | `category`, `mobile_brand_name`, `mobile_model_name`, `mobile_marketing_name`, `mobile_os_hardware_model`, `operating_system`, `operating_system_version`, `vendor_id`, `advertising_id`, `language` (STRING); `time_zone_offset_seconds` (INTEGER); `is_limited_ad_tracking` (BOOLEAN); `web_info.{browser, browser_version, hostname}` (STRING) |
| `user_properties.value` | `string_value` (STRING), `int_value` (INTEGER), `double_value` (FLOAT), `float_value` (FLOAT, currently unused), `set_timestamp_micros` (INTEGER) |
| `user_ltv` | `revenue` (FLOAT), `currency` (STRING) |
| `privacy_info` | `analytics_storage`, `ads_storage`, `uses_transient_token` (STRING) |

### 1.2 `ecommerce` RECORD (children)

| Field path | Type | Description `[DOCUMENTED]` | Used for |
|---|---|---|---|
| `ecommerce.transaction_id` | STRING | Transaction ID of the e-commerce transaction. | **Order de-duplication**; order counting |
| `ecommerce.total_item_quantity` | INTEGER | Sum of `items.quantity` in this event. | Basket size checks |
| `ecommerce.unique_items` | INTEGER | Number of unique items (by `item_id`, `item_name`, `item_brand`). | Basket size checks |
| `ecommerce.purchase_revenue_in_usd` | FLOAT | Purchase revenue in USD, standard unit. Populated for `purchase` events only. | **Revenue (preferred field)** |
| `ecommerce.purchase_revenue` | FLOAT | Purchase revenue in local currency. Populated for `purchase` events only. | Fallback only — see [currency callout](#currency-safety) |
| `ecommerce.tax_value_in_usd` / `ecommerce.tax_value` | FLOAT | Tax value in USD / local currency. | Revenue composition (diagnostic) |
| `ecommerce.shipping_value_in_usd` / `ecommerce.shipping_value` | FLOAT | Shipping value in USD / local currency. | Revenue composition (diagnostic) |
| `ecommerce.refund_value_in_usd` / `ecommerce.refund_value` | FLOAT | Refund amount in USD / local currency; populated for `refund` events only. | Net revenue (Sprint 04+) |

### 1.3 `items` RECORD (children)

One entry per item in the event; repeated for each item.

| Field path | Type | Description `[DOCUMENTED]` | Used for |
|---|---|---|---|
| `items.item_id` | STRING | Item ID. | Product key |
| `items.item_name` | STRING | Item name. | Product reporting |
| `items.item_brand` | STRING | Brand. | Category/brand analysis |
| `items.item_variant` | STRING | Variant. | Product detail analysis |
| `items.item_category` … `items.item_category5` | STRING | Category and up to four sub-categories. | Category reporting |
| `items.price_in_usd` | FLOAT | Item price in USD, standard unit. | Cross-currency-safe pricing |
| `items.price` | FLOAT | Item price in local currency. | Fallback only |
| `items.quantity` | INTEGER | Quantity; defaults to 1 if unspecified. | Basket size; units sold |
| `items.item_revenue_in_usd` | FLOAT | `price_in_usd × quantity`; populated for `purchase` events only. | Item-level revenue (preferred) |
| `items.item_revenue` | FLOAT | `price × quantity`; populated for `purchase` events only. | Fallback only |
| `items.item_refund_in_usd` / `items.item_refund` | FLOAT | Refund value per item (USD / local); `refund` events only. | Net item revenue (Sprint 04+) |
| `items.coupon` | STRING | Item-level coupon code. | Promotion analysis |
| `items.affiliation` | STRING | Supplying company / store location. | Supplier analysis |
| `items.location_id` | STRING | Location associated with the item. | Location analysis |
| `items.item_list_id` / `items.item_list_name` | STRING | List in which the item was presented. | Merchandising analysis |
| `items.item_list_index` | STRING | Position of the item in a list (typed STRING). | Position analysis |
| `items.promotion_id` / `items.promotion_name` | STRING | Promotion identifiers. | Promotion analysis |
| `items.creative_name` / `items.creative_slot` | STRING | Promotional creative metadata. | Promotion analysis |
| `items.item_params` | RECORD | REPEATED custom item parameters: `key`, `value.{string_value,int_value,double_value,float_value}`. | Custom item attributes `[UNVERIFIED — needs BigQuery]` |

### 1.4 `event_params` RECORD (structure)

| Field path | Type | Mode | Description `[DOCUMENTED]` |
|---|---|---|---|
| `event_params.key` | STRING | NULLABLE | The parameter name. |
| `event_params.value` | RECORD | NULLABLE | A record containing the parameter's value. |
| `event_params.value.string_value` | STRING | NULLABLE | Populated when the parameter is represented by a string. |
| `event_params.value.int_value` | INTEGER | NULLABLE | Populated when the parameter is represented by an integer. |
| `event_params.value.double_value` | FLOAT | NULLABLE | Populated when the parameter is represented by a double. |
| `event_params.value.float_value` | FLOAT | NULLABLE | Documented as **not currently in use** — do not rely on it. |

## 2. Important `event_params` keys

The set of keys is implementation-specific; the lists below are the keys relevant to GrowthScope's analyses for a standard web e-commerce implementation. **Whether each key actually appears in the sample dataset, and in which of `string_value` / `int_value` / `double_value` it lands, must be confirmed with the event-parameter inventory query in `sql/exploration/`** → `[UNVERIFIED — needs BigQuery]` for all rows unless noted.

Semantics below are documented across Google's Analytics help — session parameters on [About Analytics sessions](https://support.google.com/analytics/answer/9191807), page/engagement parameters on [Automatically collected events](https://support.google.com/analytics/answer/9234069), e-commerce parameters on [Recommended events](https://support.google.com/analytics/answer/9267735) and [Measure ecommerce](https://developers.google.com/analytics/devguides/collection/ga4/ecommerce) — and the sample dataset is documented to use the standard web e-commerce implementation plus enhanced measurement ([dataset page](https://developers.google.com/analytics/bigquery/web-ecommerce-demo-dataset)).

| Key | Expected value column | Meaning | Used by |
|---|---|---|---|
| `ga_session_id` | `int_value` | Session identifier — generated as the **timestamp in seconds when the session started**; unique per user, not globally ([source](https://support.google.com/analytics/answer/9191807)). | **Session key** `(user_pseudo_id, ga_session_id)`; all session-grain metrics |
| `ga_session_number` | `int_value` | Ordinal of the session for that user (1 = first). | New vs returning session analysis |
| `page_location` | `string_value` | Full page URL (≤ 1,000 chars). | Page/landing analysis; referrer checks |
| `page_title` | `string_value` | Page title (≤ 300 chars). | Page reporting |
| `page_referrer` | `string_value` | Referring page URL (≤ 420 chars). | Referral context |
| `source` | `string_value` | Campaign source (`utm_source`) for tagged traffic. | Session campaign context |
| `medium` | `string_value` | Campaign medium (`utm_medium`). | Session campaign context |
| `campaign` | `string_value` | Campaign name (`utm_campaign`). | Session campaign context |
| `term` | `string_value` | Campaign term / keyword (`utm_term`). | Paid search analysis |
| `content` | `string_value` | Campaign content (`utm_content`). | Creative analysis |
| `gclid` | `string_value` | Google Click ID. | Paid-search detection (structured alternative: `collected_traffic_source.gclid`) |
| `engagement_time_msec` | `int_value` | Engaged time in milliseconds. | Engagement diagnostics |
| `engaged_session_event` | `int_value` | `1` when the session is counted as engaged. | Engaged-session share |
| `entrances` | `int_value` | `1` when the page was the first in the session. | Landing-page analysis |
| `percent_scrolled` | `int_value` | Scroll depth percentage reached (enhanced measurement, e.g. `90`). | Content engagement diagnostics |
| `transaction_id` | `string_value` | Transaction ID (duplicate of `ecommerce.transaction_id` for `purchase`). | Order de-duplication fallback |
| `value` | `double_value` | Monetary value attached to the event. | Revenue cross-checks (`event_value_in_usd` derives from it) |
| `currency` | `string_value` | Currency of the `value` parameter. | Interpreting `value` / local-currency fields |
| `tax` | `double_value` | Tax amount passed with the purchase event. | Revenue composition |
| `shipping` | `double_value` | Shipping amount passed with the purchase event. | Revenue composition |
| `coupon` | `string_value` | Coupon code at event level (item-level code: `items.coupon`). | Promotion analysis |
| `payment_type` | `string_value` | Payment method. | Checkout diagnostics |
| `firebase_event_origin` | `string_value` | Origin marker (e.g. `web`). | Platform sanity checks |
| `debug_mode` | `int_value` | `1` when the event came from debug mode. | **Exclusion filter** for marketing analysis |

> [!NOTE]
> The current export documentation also mentions `event_original_occurrence_timestamp` (original device time for events ingested after the standard 72-hour window). It is not listed among the keys above because its presence in this 2020–21 export is unverified — `[UNVERIFIED — needs BigQuery]`.

## 3. Callouts

### Currency safety

> [!WARNING]
> **`purchase_revenue` is not a safe cross-currency field.** The schema defines `purchase_revenue` as *local currency* and `purchase_revenue_in_usd` as *USD with standard unit* ([source](https://support.google.com/analytics/answer/7029846)), so they are two fields with two units, not two names for one value. Summing `purchase_revenue` across events whose currencies differ adds dollars to euros and produces a meaningless total. **GrowthScope therefore always uses `purchase_revenue_in_usd` / `price_in_usd` / `item_revenue_in_usd` for revenue math.**
>
> A second, commonly repeated claim — that `purchase_revenue` is populated *only* when the event currency matches the property currency, and is `NULL` otherwise — is **`[UNVERIFIED]` and not supported by the documentation reviewed for this project** (see `dataset_research.md` §10.2, where it is recorded as `[UNRESOLVED]`). Do not design around it. It is tested empirically by `sql/exploration/06_purchase_revenue_audit.sql` (query 2, `store_currency_null_usd_present`): if a NULL asymmetry appears there, it is reported as an **observed finding with that query as evidence**, never as documented behaviour.

### Timestamps are microseconds

> [!IMPORTANT]
> `event_timestamp`, `event_previous_timestamp` and `user_first_touch_timestamp` are **INTEGER microseconds since the Unix epoch (UTC)** — one second is `1_000_000`. Do not compare them to seconds-based values, and do not cast them to `DATE` naively: `event_date` (STRING `YYYYMMDD`) is expressed in the **property timezone**, so a UTC conversion of `event_timestamp` may fall on a different day near midnight. Use `event_date` for day-grain grouping, `event_timestamp` for ordering within a session.

### Obfuscated dataset

> [!NOTE]
> Values (`<Other>`, `NULL`, `''`, placeholder strings) are partly synthetic. Coverage of `device`, `geo`, `traffic_source` and item fields may be imperfect by design. Any metric derived from this dataset must carry the reliability note from [`metric_dictionary.md`](metric_dictionary.md).

## 4. Re-verification plan (Sprint 02)

Every `[UNVERIFIED — needs BigQuery]` row above is closed by running, in order:

1. **Dataset inventory** — table list, row counts, date coverage, total bytes (confirms the `events_YYYYMMDD` pattern and the 2020-11-01 → 2021-01-31 window).
2. **Column presence** — which schema columns exist in the 2020–21 export (notably `session_traffic_source_last_click`, `privacy_info`, `batch_*`).
3. **Event-parameter inventory** — distinct `event_params.key` values and their populated value columns (confirms section 2).
4. **Item-field coverage** — share of `items` rows with `item_id`, `item_name`, `item_category`.
5. **Currency checks** — distribution of `currency` parameter values and the `purchase_revenue` vs `purchase_revenue_in_usd` NULL pattern.

Results are recorded in `docs/data_quality_audit.md` (Sprint 01 skeleton, Sprint 02 verified) and this document is updated in place.
