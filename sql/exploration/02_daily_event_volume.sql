-- ============================================================================
-- GROWTHSCOPE - Sprint 01 / Data Discovery (GA4 public sample ecommerce)
-- FILE      : 02_daily_event_volume.sql
-- PURPOSE   : Measure the basic shape of traffic in the window:
--               Q1 - events per day, distinct users per day, events per user
--               Q2 - distribution of events per user per day (spread, not
--                    just the average - GA4 traffic is heavily right-skewed)
--               Q3 - correct period-level distinct users (to contrast with the
--                    WRONG "sum of daily users" number)
--               Q4 - data-quality check: do shard suffix and event_date agree?
-- TABLES    : `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
-- SCAN RISK : LOW - 3 shards, projects event_date / user_pseudo_id only.
-- OUTPUT    : Q1: one row per event_date.
--             Q2: one row per event_date (distribution summary).
--             Q3: one row (whole window).
--             Q4: one row (whole window, data-quality counts).
-- CAVEATS   : - Summing the daily distinct-user counts does NOT give distinct
--               users for the period. A user active on all 3 days is counted
--               3 times. Only COUNT(DISTINCT user_pseudo_id) over the whole
--               window is correct (that is why Q3 exists).
--             - An "event count is not a session count": one session can emit
--               dozens of events (scroll, page_view, user_engagement, ...).
--               Sessions are audited separately in 07_session_feasibility.sql.
--             - The obfuscated sample contains placeholder values (NULL, '',
--               `<Other>`); rows with a missing user_pseudo_id cannot be
--               attributed to a user - see 03_user_identification.sql.
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
-- Tip            : if you widen the window, expect one output row per day;
--                  the shard must exist, otherwise the day simply does not
--                  appear in the results (Q4 in 00_project_settings.sql lists
--                  which shards exist).
-- ----------------------------------------------------------------------------

-- ============================================================================
-- QUERY 1 - Daily volume: events, distinct users, events per user
-- Grain    : one row per event_date (YYYYMMDD string as stored by GA4).
-- Note     : `event_date` is a STRING in YYYYMMDD format, not a DATE. Compare
--            with `TIMESTAMP_MICROS(event_timestamp)` when you need a real
--            timestamp (event_timestamp is microseconds, UTC).
-- ============================================================================
WITH window_events AS (
  -- Project only what the aggregation needs. `event_date` and
  -- `user_pseudo_id` are the only columns this query reads.
  SELECT
    event_date,
    user_pseudo_id
  FROM
    `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE
    _TABLE_SUFFIX BETWEEN '20201101' AND '20201103' -- [WINDOW]
),
daily AS (
  SELECT
    event_date,
    COUNT(*) AS event_count,
    -- COUNT(DISTINCT ...) silently ignores NULLs. Rows with a missing
    -- user_pseudo_id are still counted in event_count but cannot be counted
    -- as users - that asymmetry is measured explicitly in file 03.
    COUNT(DISTINCT user_pseudo_id) AS distinct_users,
    -- SAFE_DIVIDE returns NULL instead of raising a "division by zero" error
    -- when a day has events but (theoretically) no distinct users.
    ROUND(SAFE_DIVIDE(COUNT(*), COUNT(DISTINCT user_pseudo_id)), 2) AS events_per_user
  FROM
    window_events
  GROUP BY
    event_date
)
SELECT
  event_date,
  event_count,
  distinct_users,
  events_per_user
FROM
  daily
ORDER BY
  event_date;

-- ============================================================================
-- QUERY 2 - Events per user per day: distribution, not just the mean
-- Grain    : one row per event_date.
-- Why      : the mean in Q1 hides the shape. A small share of users typically
--            produces a very long tail of events; the median and p95 tell you
--            whether events_per_user is driven by typical users or outliers.
--            This matters before building any per-user metric or scoring model.
-- Method   : 1) count events per (event_date, user_pseudo_id);
--            2) summarize that distribution per day.
-- ============================================================================
WITH window_events AS (
  SELECT
    event_date,
    user_pseudo_id
  FROM
    `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE
    _TABLE_SUFFIX BETWEEN '20201101' AND '20201103' -- [WINDOW]
),
user_day AS (
  -- One row per user-day. Rows with a NULL user_pseudo_id are excluded:
  -- grouping NULLs would lump together unrelated events from different users
  -- under a single fake "user". Their volume is measured in file 03.
  SELECT
    event_date,
    user_pseudo_id,
    COUNT(*) AS events_in_user_day
  FROM
    window_events
  WHERE
    user_pseudo_id IS NOT NULL
    AND user_pseudo_id != ''
  GROUP BY
    event_date,
    user_pseudo_id
)
SELECT
  event_date,
  COUNT(*) AS user_days, -- = distinct users observed that day
  MIN(events_in_user_day) AS min_events_per_user,
  ROUND(AVG(events_in_user_day), 2) AS avg_events_per_user,
  -- APPROX_QUANTILES: an approximate but very cheap quantile (bounded memory,
  -- same order of magnitude as exact for this purpose). [OFFSET(50)] = median,
  -- [OFFSET(95)] = p95. For exact quantiles use PERCENTILE_CONT (more memory).
  APPROX_QUANTILES(events_in_user_day, 100)[OFFSET(50)] AS approx_median_events_per_user,
  APPROX_QUANTILES(events_in_user_day, 100)[OFFSET(95)] AS approx_p95_events_per_user,
  MAX(events_in_user_day) AS max_events_per_user
FROM
  user_day
GROUP BY
  event_date
ORDER BY
  event_date;

-- ============================================================================
-- QUERY 3 - Distinct users for the WHOLE window (the correct period metric)
-- Grain    : one row.
-- Why      : run this next to Q1 and compare:
--              SUM(distinct_users from Q1)  >=  distinct_users here
--            The difference is user overlap between days (users active on more
--            than one day are double/triple counted by the sum). This is the
--            classic "do not sum a deduplicated metric" mistake.
-- ============================================================================
WITH window_events AS (
  SELECT
    user_pseudo_id
  FROM
    `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE
    _TABLE_SUFFIX BETWEEN '20201101' AND '20201103' -- [WINDOW]
)
SELECT
  COUNT(*) AS event_count_in_window,
  COUNT(DISTINCT user_pseudo_id) AS distinct_users_in_window
FROM
  window_events;

-- ============================================================================
-- QUERY 4 - Data-quality check: shard suffix vs logical `event_date`
-- Grain    : one row.
-- Why      : the wildcard table is split physically by day (`_TABLE_SUFFIX`),
--            and each row also carries the logical event date (`event_date`).
--            In a healthy daily export they agree. A non-zero mismatch count
--            is a signal: late-arriving events, reprocessing, or a property
--            timezone quirk. Knowing it BEFORE window-based analysis prevents
--            silently wrong day-over-day comparisons.
-- Note     : this only compares within the scanned window; a shard's content
--            is not checked against neighbouring shards.
-- ============================================================================
WITH window_events AS (
  SELECT
    _TABLE_SUFFIX AS shard_suffix,
    event_date
  FROM
    `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE
    _TABLE_SUFFIX BETWEEN '20201101' AND '20201103' -- [WINDOW]
)
SELECT
  COUNT(*) AS events_scanned,
  COUNTIF(shard_suffix = event_date) AS events_where_shard_matches_event_date,
  COUNTIF(shard_suffix != event_date) AS events_where_shard_differs_from_event_date
FROM
  window_events;
