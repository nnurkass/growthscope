-- ============================================================================
-- GROWTHSCOPE - Sprint 01 / Data Discovery (GA4 public sample ecommerce)
-- FILE      : 04_event_parameters.sql
-- PURPOSE   : Learn how to read the REPEATED RECORD `event_params`, measure
--             which parameter keys exist, and unpack the two parameter sets
--             GrowthScope cares about:
--               Q1 - coverage per parameter key across ALL events in the window
--               Q2 - session_start pivot: traffic-source / acquisition params
--               Q3 - purchase pivot: e-commerce params next to the ecommerce
--                    RECORD (GA4 writes the same values in two places)
--               Q4 - purchase availability: parameter vs ecommerce RECORD
-- TABLES    : `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
-- SCAN RISK : MEDIUM - Q1 UNNESTs the parameter array of every event in the
--             window. Q2-Q4 read the same shards but touch far fewer rows.
--             Keep the 3-day window; dry-run before widening (see file 00).
-- OUTPUT    : Q1: one row per parameter key (all events).
--             Q2: one row per session_start event.
--             Q3: one row per purchase event (params + ecommerce RECORD).
--             Q4: one row (availability counters for purchase).
-- CAVEATS   : - event_params is ARRAY<STRUCT<key, value>>. The value STRUCT
--               has FOUR columns: string_value, int_value, float_value,
--               double_value. Which one is populated depends on how the
--               collector serialized the value - the same logical field can
--               appear in different columns across implementations. The
--               official schema notes `float_value` is "not currently in use",
--               so numbers realistically live in int_value or double_value.
--               Documentation: https://support.google.com/analytics/answer/7029846
--             - A scalar subquery like
--                 (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'x')
--               returns an ERROR at run time if a tag emitted the same key
--               twice for one event. Parenthesized extraction patterns that
--               solve this are shown in the "value columns" comment below.
--             - `items` rows can also carry custom `item_params` (same
--               key/value STRUCT shape) - not queried here.
-- READ-ONLY : SELECT statements only. No DDL/DML, no temp tables, no exports.
-- STATUS    : UNVERIFIED - BigQuery was not available in the build environment.
--             No results are reproduced here; run the file to produce them.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- WINDOW (single source of truth)
-- Default window : 2020-11-01 .. 2020-11-03 (3 days)
-- Predicate      : _TABLE_SUFFIX BETWEEN '20201101' AND '20201103'
-- To change      : edit the two date literals. Each query below contains that
--                  predicate exactly once, always in this exact form.
-- ----------------------------------------------------------------------------

-- ----------------------------------------------------------------------------
-- HOW TO EXTRACT ONE PARAMETER VALUE - the patterns used in this file
--
-- Why a correlated scalar subquery instead of a JOIN:
--   `FROM t, UNNEST(t.event_params) p WHERE p.key = 'x'` multiplies rows -
--   an event with 20 parameters becomes 20 rows. Any COUNT(*)/COUNT(DISTINCT)
--   over that joined result inflates or distorts counts, and you must GROUP BY
--   every original column to get back to event grain. The scalar subquery
--   keeps the original event grain (one row per event) and costs almost
--   nothing on a small array.
--
-- Safe extraction by target type (copy/paste, replace 'key_name'):
--   STRING : COALESCE(
--              (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'key_name'),
--              CAST((SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'key_name') AS STRING),
--              CAST((SELECT value.double_value FROM UNNEST(event_params) WHERE key = 'key_name') AS STRING)
--            )
--   INT64  : COALESCE(
--              (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'key_name'),
--              CAST((SELECT value.double_value FROM UNNEST(event_params) WHERE key = 'key_name') AS INT64)
--            )
--   FLOAT64: COALESCE(
--              (SELECT value.double_value FROM UNNEST(event_params) WHERE key = 'key_name'),
--              CAST((SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'key_name') AS FLOAT64)
--            )
--
-- HARDENING: if an implementation can emit the same key twice per event, the
-- scalar subquery above fails with "Scalar subquery produced more than one
-- element". Any aggregate hides that: ANY_VALUE() picks one deterministically
-- only in the sense of "one of them", ARRAY_AGG + LIMIT 1 is explicit:
--   (SELECT ANY_VALUE(value.string_value) FROM UNNEST(event_params) WHERE key = 'key_name')
-- Prefer the plain pattern while exploring (it fails loudly), and switch to
-- ANY_VALUE only after you confirm duplicates are legitimate for the key.
-- ----------------------------------------------------------------------------

-- ============================================================================
-- QUERY 1 - Parameter coverage: which keys exist, how often, in which column?
-- Grain    : one row per parameter key.
-- Why      : "the parameter exists" is an assumption until measured. This
--            query proves which keys this implementation actually emits and
--            shows which value column carries them (string vs int vs double).
-- Columns  :
--   param_key            - the key inside event_params
--   event_key_rows       - number of (event, key) rows
--                          (a key emitted twice on one event would count twice)
--   distinct_event_names - how many different event names carry this key
--   string_values / int_values / double_values
--                        - rows whose value arrived in that column
--   float_values         - kept for completeness; the official schema says
--                          this column is not currently in use
-- ============================================================================
WITH window_events AS (
  SELECT
    event_name,
    event_params
  FROM
    `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE
    _TABLE_SUFFIX BETWEEN '20201101' AND '20201103' -- [WINDOW]
),
exploded_params AS (
  -- UNNEST turns the repeated field into one row per parameter. This is the
  -- point of the query (we WANT per-key rows), but remember the row fan-out:
  -- never compute event counts from `exploded_params`.
  SELECT
    event_name,
    param.key AS param_key,
    param.value.string_value IS NOT NULL AS is_string,
    param.value.int_value IS NOT NULL AS is_int,
    param.value.float_value IS NOT NULL AS is_float,
    param.value.double_value IS NOT NULL AS is_double
  FROM
    window_events,
    UNNEST(event_params) AS param
)
SELECT
  param_key,
  COUNT(*) AS event_key_rows,
  COUNT(DISTINCT event_name) AS distinct_event_names,
  COUNTIF(is_string) AS string_values,
  COUNTIF(is_int) AS int_values,
  COUNTIF(is_float) AS float_values,
  COUNTIF(is_double) AS double_values
FROM
  exploded_params
GROUP BY
  param_key
ORDER BY
  event_key_rows DESC;

-- ============================================================================
-- QUERY 2 - session_start pivot: acquisition / traffic-source parameters
-- Grain    : one row per session_start event.
-- Why      : GA4 attaches the session's traffic source (source, medium,
--            campaign, term, content, gclid) to the session_start event.
--            This is the raw material for channel/attribution analysis.
-- Manual_* : GA4 can ALSO emit tag-declared UTM overrides under keys such as
--            `manual_source`, `manual_medium`, `manual_campaign` (the schema's
--            `collected_traffic_source` RECORD documents the same concept).
--            Availability is implementation-dependent - an empty manual_* is
--            normal, which is exactly why Q1 measured coverage first.
-- Effective: the *_effective columns show the COALESCE business rule
--            "prefer the collected value, fall back to the manual override".
--            Encode the rule ONCE here instead of in every downstream query.
-- ============================================================================
WITH session_start_events AS (
  SELECT
    user_pseudo_id,
    event_date,
    event_timestamp,
    TIMESTAMP_MICROS(event_timestamp) AS event_ts_utc,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS ga_session_id,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_number') AS ga_session_number,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'source') AS source,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'medium') AS medium,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'campaign') AS campaign,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'term') AS term,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'content') AS content,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'gclid') AS gclid,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'manual_source') AS manual_source,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'manual_medium') AS manual_medium,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'manual_campaign') AS manual_campaign
  FROM
    `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE
    event_name = 'session_start'
    AND _TABLE_SUFFIX BETWEEN '20201101' AND '20201103' -- [WINDOW]
)
SELECT
  user_pseudo_id,
  event_date,
  event_ts_utc,
  ga_session_id,
  ga_session_number,
  source,
  medium,
  campaign,
  term,
  content,
  gclid,
  manual_source,
  manual_medium,
  manual_campaign,
  COALESCE(source, manual_source) AS source_effective,
  COALESCE(medium, manual_medium) AS medium_effective,
  COALESCE(campaign, manual_campaign) AS campaign_effective
FROM
  session_start_events
ORDER BY
  event_timestamp;

-- ============================================================================
-- QUERY 3 - purchase pivot: e-commerce params AND the ecommerce RECORD
-- Grain    : one row per purchase event.
-- Why      : GA4's recommended ecommerce implementation writes transaction
--            fields in TWO places:
--              1) event_params keys: transaction_id, value, currency, tax,
--                 shipping, coupon, payment_type (what the tag sent), and
--              2) the structured `ecommerce` RECORD (what GA4 processed).
--            Seeing both side by side shows which one is populated in this
--            dataset - the decision "which source is authoritative" belongs in
--            Sprint 02, based on this evidence.
-- Note     : `value` is a raw event parameter and may exclude or include
--            shipping/tax depending on the implementation - it is NOT a safe
--            revenue field. Revenue fields are audited in 06.
-- ============================================================================
WITH purchase_events AS (
  SELECT
    user_pseudo_id,
    event_date,
    event_timestamp,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS ga_session_id,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'transaction_id') AS param_transaction_id,
    COALESCE(
      (SELECT value.double_value FROM UNNEST(event_params) WHERE key = 'value'),
      CAST((SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'value') AS FLOAT64)
    ) AS param_value,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'currency') AS param_currency,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'coupon') AS param_coupon,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'payment_type') AS param_payment_type,
    ecommerce.transaction_id AS record_transaction_id,
    ecommerce.purchase_revenue AS record_purchase_revenue,
    ecommerce.purchase_revenue_in_usd AS record_purchase_revenue_in_usd,
    ecommerce.tax_value AS record_tax_value,
    ecommerce.shipping_value AS record_shipping_value,
    ARRAY_LENGTH(items) AS item_row_count
  FROM
    `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE
    event_name = 'purchase'
    AND _TABLE_SUFFIX BETWEEN '20201101' AND '20201103' -- [WINDOW]
)
SELECT
  user_pseudo_id,
  event_date,
  event_timestamp,
  ga_session_id,
  param_transaction_id,
  param_value,
  param_currency,
  param_coupon,
  param_payment_type,
  record_transaction_id,
  record_purchase_revenue,
  record_purchase_revenue_in_usd,
  record_tax_value,
  record_shipping_value,
  item_row_count
FROM
  purchase_events
ORDER BY
  event_timestamp;

-- ============================================================================
-- QUERY 4 - purchase availability counters: parameter vs ecommerce RECORD
-- Grain    : one row.
-- Why      : Q3 shows individual rows; this counts them. Column names encode
--            the source: `param_*` = event_params key, `record_*` = the
--            `ecommerce` RECORD field. Use it to decide which source has
--            enough coverage to build on (answer recorded in Sprint 02).
-- Warning  : do NOT sum revenue here. This sprint audits availability only;
--            duplicate and currency risks are quantified in 06.
-- ============================================================================
WITH purchase_events AS (
  SELECT
    ecommerce.transaction_id AS record_transaction_id,
    ecommerce.purchase_revenue AS record_purchase_revenue,
    ecommerce.purchase_revenue_in_usd AS record_purchase_revenue_usd,
    ecommerce.tax_value AS record_tax_value,
    ecommerce.shipping_value AS record_shipping_value,
    ARRAY_LENGTH(items) AS item_row_count,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'transaction_id') AS param_transaction_id,
    COALESCE(
      (SELECT value.double_value FROM UNNEST(event_params) WHERE key = 'value'),
      CAST((SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'value') AS FLOAT64)
    ) AS param_value,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'currency') AS param_currency,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'coupon') AS param_coupon,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'payment_type') AS param_payment_type
  FROM
    `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE
    event_name = 'purchase'
    AND _TABLE_SUFFIX BETWEEN '20201101' AND '20201103' -- [WINDOW]
)
SELECT
  COUNT(*) AS purchase_events,
  COUNTIF(param_transaction_id IS NOT NULL) AS param_transaction_id_present,
  COUNTIF(record_transaction_id IS NOT NULL AND record_transaction_id != '') AS record_transaction_id_present,
  COUNTIF(param_value IS NOT NULL) AS param_value_present,
  COUNTIF(param_currency IS NOT NULL) AS param_currency_present,
  COUNTIF(param_coupon IS NOT NULL) AS param_coupon_present,
  COUNTIF(param_payment_type IS NOT NULL) AS param_payment_type_present,
  COUNTIF(record_purchase_revenue IS NOT NULL) AS record_purchase_revenue_present,
  COUNTIF(record_purchase_revenue_usd IS NOT NULL) AS record_purchase_revenue_usd_present,
  COUNTIF(record_tax_value IS NOT NULL) AS record_tax_value_present,
  COUNTIF(record_shipping_value IS NOT NULL) AS record_shipping_value_present,
  COUNTIF(item_row_count > 0) AS events_with_item_rows
FROM
  purchase_events;
