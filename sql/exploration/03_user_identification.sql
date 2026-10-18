-- ============================================================================
-- GROWTHSCOPE - Sprint 01 / Data Discovery (GA4 public sample ecommerce)
-- FILE      : 03_user_identification.sql
-- PURPOSE   : Audit the user-identifier columns the whole platform depends on:
--               Q1 - how many events carry a usable user_pseudo_id / user_id /
--                    user_first_touch_timestamp (and how many do not)?
--               Q2 - is user_first_touch_timestamp internally consistent
--                    (one value per user, never after the user's last event)?
--               Q3 - how many users were first seen INSIDE the window vs
--                    BEFORE it (returning users)?
-- TABLES    : `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
-- SCAN RISK : LOW - 3 shards, projects 3 columns only.
-- OUTPUT    : Q1: one row (window-wide summary + missing-value shares).
--             Q2: one row (consistency counters).
--             Q3: one row (first-seen split).
-- CAVEATS   : - LIMITED OBSERVABILITY: this export is event data, not a user
--               registry. The absence of events does NOT prove a user never
--               existed: consent choices, ad blockers, cookieless pings,
--               offline/backfilled uploads and the 3-day window all hide
--               activity. Every "new user" statement must be scoped to
--               "first observed inside this window".
--             - user_pseudo_id is a COOKIE/device-instance identifier, not a
--               person. The same person on two devices/browsers = two pseudo
--               ids; clearing cookies starts a new one. user_id (set when a
--               user signs in) is the only cross-device signal and it is
--               usually empty on most events.
--             - COUNT(DISTINCT x) ignores NULLs. A "distinct users" number
--               therefore always means "users with a non-null x".
--             - The obfuscated sample intentionally contains placeholder
--               values (NULL, '', `<Other>`), so treat empty strings as
--               missing - they are checked alongside NULL everywhere here.
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

-- ============================================================================
-- QUERY 1 - Identifier availability in the window (single summary row)
-- Grain    : one row.
-- Column map:
--   total_events                        - all event rows in the window
--   events_missing_user_pseudo_id       - NULL or '' pseudo id
--   pct_missing_user_pseudo_id          - share of total_events (%)
--   distinct_user_pseudo_ids            - non-null, non-empty pseudo ids
--   events_with_user_id                 - events carrying a signed-in user_id
--   pct_events_with_user_id             - share of total_events (%)
--   distinct_user_ids                   - distinct non-empty user_id values
--   events_missing_first_touch_ts       - NULL user_first_touch_timestamp
--   pct_missing_first_touch_ts          - share of total_events (%)
-- ============================================================================
WITH window_events AS (
  -- Only the three identifier columns are read - the GA4 tables are wide and
  -- columnar, so projecting exactly what you need is the cheapest scan.
  SELECT
    user_pseudo_id,
    user_id,
    user_first_touch_timestamp
  FROM
    `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE
    _TABLE_SUFFIX BETWEEN '20201101' AND '20201103' -- [WINDOW]
)
SELECT
  COUNT(*) AS total_events,
  COUNTIF(user_pseudo_id IS NULL OR user_pseudo_id = '') AS events_missing_user_pseudo_id,
  ROUND(
    100 * SAFE_DIVIDE(
      COUNTIF(user_pseudo_id IS NULL OR user_pseudo_id = ''),
      COUNT(*)
    ),
    3
  ) AS pct_missing_user_pseudo_id,
  COUNT(DISTINCT user_pseudo_id) AS distinct_user_pseudo_ids,
  COUNTIF(user_id IS NOT NULL AND user_id != '') AS events_with_user_id,
  ROUND(
    100 * SAFE_DIVIDE(
      COUNTIF(user_id IS NOT NULL AND user_id != ''),
      COUNT(*)
    ),
    3
  ) AS pct_events_with_user_id,
  COUNT(DISTINCT user_id) AS distinct_user_ids,
  COUNTIF(user_first_touch_timestamp IS NULL) AS events_missing_first_touch_ts,
  ROUND(
    100 * SAFE_DIVIDE(
      COUNTIF(user_first_touch_timestamp IS NULL),
      COUNT(*)
    ),
    3
  ) AS pct_missing_first_touch_ts
FROM
  window_events;

-- ============================================================================
-- QUERY 2 - Is user_first_touch_timestamp internally consistent?
-- Grain    : one row (counter columns; read it like a test result).
-- Expectation: for a given user_pseudo_id, the first-touch timestamp is a
--            property of the USER, so it should be
--              (a) exactly one value across that user's events, and
--              (b) never LATER than any of the user's event timestamps.
--            Non-zero counters do not necessarily mean a bug: late attribution
--            updates and the obfuscation of this sample can produce both.
--            But they bound how much trust "first touch" deserves downstream.
-- Units    : user_first_touch_timestamp and event_timestamp are INTEGER
--            microseconds since the UNIX epoch (UTC).
-- ============================================================================
WITH window_events AS (
  SELECT
    user_pseudo_id,
    user_first_touch_timestamp,
    event_timestamp
  FROM
    `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE
    _TABLE_SUFFIX BETWEEN '20201101' AND '20201103' -- [WINDOW]
),
per_user AS (
  SELECT
    user_pseudo_id,
    COUNT(DISTINCT user_first_touch_timestamp) AS distinct_first_touch_values,
    MIN(user_first_touch_timestamp) AS first_touch_ts_min,
    MAX(event_timestamp) AS last_event_ts_max
  FROM
    window_events
  WHERE
    user_pseudo_id IS NOT NULL
    AND user_pseudo_id != ''
    AND user_first_touch_timestamp IS NOT NULL
  GROUP BY
    user_pseudo_id
)
SELECT
  COUNT(*) AS users_with_first_touch,
  COUNTIF(distinct_first_touch_values > 1) AS users_with_multiple_first_touch_values,
  COUNTIF(first_touch_ts_min > last_event_ts_max) AS users_where_first_touch_is_after_last_event
FROM
  per_user;

-- ============================================================================
-- QUERY 3 - First seen inside vs before the window
-- Grain    : one row.
-- Why      : "new user" and "returning user" are the most misused GA4
--            concepts. This splits users by whether their first-ever touch is
--            INSIDE the observed window - which is the only claim the data can
--            support. A user "first seen before the window" is simply older
--            than our data slice.
-- Boundary : the window start is DERIVED from the data (MIN(_TABLE_SUFFIX) of
--            the scanned shards), so changing the WINDOW block above is
--            enough - there is no second date literal to keep in sync.
-- Caveat   : user_first_touch_timestamp is UTC (microseconds); event_date /
--            _TABLE_SUFFIX follow the property timezone. Around midnight the
--            split is therefore approximate - acceptable for a presence
--            audit, not for financial reporting.
-- ============================================================================
WITH window_events AS (
  SELECT
    _TABLE_SUFFIX AS shard_suffix,
    user_pseudo_id,
    user_first_touch_timestamp
  FROM
    `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE
    _TABLE_SUFFIX BETWEEN '20201101' AND '20201103' -- [WINDOW]
),
per_user AS (
  SELECT
    user_pseudo_id,
    MIN(user_first_touch_timestamp) AS first_touch_ts_min
  FROM
    window_events
  WHERE
    user_pseudo_id IS NOT NULL
    AND user_pseudo_id != ''
    AND user_first_touch_timestamp IS NOT NULL
  GROUP BY
    user_pseudo_id
)
SELECT
  COUNT(*) AS users_with_first_touch,
  COUNTIF(
    FORMAT_DATE('%Y%m%d', TIMESTAMP_MICROS(first_touch_ts_min))
      >= (SELECT MIN(shard_suffix) FROM window_events)
  ) AS users_first_seen_inside_window,
  COUNTIF(
    FORMAT_DATE('%Y%m%d', TIMESTAMP_MICROS(first_touch_ts_min))
      < (SELECT MIN(shard_suffix) FROM window_events)
  ) AS users_first_seen_before_window
FROM
  per_user;
