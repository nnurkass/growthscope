-- ============================================================================
-- GROWTHSCOPE - Sprint 01 / Data Discovery (GA4 public sample ecommerce)
-- FILE      : 05_funnel_event_audit.sql
-- PURPOSE   : Presence audit of the 13 events GrowthScope intends to model:
--               page_view, view_item_list, view_item, add_to_cart,
--               remove_from_cart, view_cart, begin_checkout, add_shipping_info,
--               add_payment_info, purchase, refund, session_start, first_visit.
--             For each event: how many times it occurred, in how many distinct
--             users and sessions.
--             THIS IS NOT A FUNNEL CONVERSION RATE. Event-level presence is a
--             PREREQUISITE for funnel models (Sprint 02), not the funnel:
--               - presence says nothing about step ORDER inside a session;
--               - distinct users per step overlap between steps;
--               - purchases are not de-duplicated yet (see 06);
--               - the session key must be proven first (see 07).
-- TABLES    : `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
-- SCAN RISK : MEDIUM - the window's shards are read and the ga_session_id
--             parameter is extracted per event (UNNEST under the hood). Still
--             bounded to 3 days; dry-run before widening the window.
-- OUTPUT    : Q1: exactly one row per expected event (13 rows; missing events
--                  appear with zeros instead of disappearing).
--             Q2: one row per (event_date, expected event) grid cell.
-- CAVEATS   : - EVENT COUNTS ARE NOT SESSION COUNTS. One session emits many
--               events (page_view, scroll, ...); distinct_sessions is the
--               session-level view and is the column to compare between steps.
--             - distinct_sessions only counts events where BOTH user_pseudo_id
--               and ga_session_id exist. Events missing either key are counted
--               in events_without_full_session_key. File 07 quantifies the gap.
--             - The exact question "which users progressed step 1 -> step 2"
--               needs ordered session logic; that is a Sprint 02 deliverable.
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
-- QUERY 1 - Per-event presence audit (zero-filled, ordered by journey position)
-- Grain    : one row per expected event name (13 rows).
-- Method   : build the expected list first, aggregate what actually exists,
--            then LEFT JOIN so a never-observed event shows 0 instead of
--            silently vanishing from the report - absence IS the finding.
-- Columns  :
--   step_order   - expected journey position (reading aid; session_start and
--                  first_visit sit at the top because they open/annotate the
--                  session, refund sits last because it reverses a purchase)
--   event_count                 - event rows in the window
--   distinct_users              - users (non-null user_pseudo_id) emitting it
--   distinct_sessions           - distinct (user_pseudo_id | ga_session_id)
--                                 keys emitting it
--   events_without_full_session_key - rows missing user_pseudo_id or
--                                 ga_session_id (cannot be session-keyed)
-- ============================================================================
WITH expected_events AS (
  -- The expected list is a PROJECT DECISION, not a GA4 fact. It mirrors the
  -- ecommerce journey GrowthScope wants to measure. Editing it here and in
  -- 01_event_inventory.sql (query 3) keeps the two files consistent.
  SELECT 1 AS step_order, 'session_start' AS event_name
  UNION ALL SELECT 2, 'first_visit'
  UNION ALL SELECT 3, 'page_view'
  UNION ALL SELECT 4, 'view_item_list'
  UNION ALL SELECT 5, 'view_item'
  UNION ALL SELECT 6, 'add_to_cart'
  UNION ALL SELECT 7, 'remove_from_cart'
  UNION ALL SELECT 8, 'view_cart'
  UNION ALL SELECT 9, 'begin_checkout'
  UNION ALL SELECT 10, 'add_shipping_info'
  UNION ALL SELECT 11, 'add_payment_info'
  UNION ALL SELECT 12, 'purchase'
  UNION ALL SELECT 13, 'refund'
),
window_events AS (
  -- Extract ga_session_id ONCE per event with a correlated scalar subquery
  -- (not a JOIN + UNNEST, which would fan out rows and inflate counts - see
  -- the extraction note at the top of 04_event_parameters.sql).
  -- ga_session_id is an INTEGER in int_value: it is the session-start timestamp
  -- in seconds, NOT a sequential id (see 07_session_feasibility.sql).
  SELECT
    event_name,
    user_pseudo_id,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS ga_session_id
  FROM
    `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE
    event_name IN (SELECT event_name FROM expected_events)
    AND _TABLE_SUFFIX BETWEEN '20201101' AND '20201103' -- [WINDOW]
),
observed AS (
  SELECT
    event_name,
    COUNT(*) AS event_count,
    COUNT(DISTINCT user_pseudo_id) AS distinct_users,
    -- Session key = user_pseudo_id + ga_session_id. The ga_session_id value
    -- alone is NOT unique across users (proven in file 07), so the composite
    -- key is mandatory. IF(...) yields NULL when either part is missing, and
    -- COUNT(DISTINCT ...) ignores NULLs - those rows are surfaced separately
    -- instead of silently becoming fake sessions.
    COUNT(
      DISTINCT IF(
        user_pseudo_id IS NOT NULL
        AND user_pseudo_id != ''
        AND ga_session_id IS NOT NULL,
        CONCAT(user_pseudo_id, '|', CAST(ga_session_id AS STRING)),
        NULL
      )
    ) AS distinct_sessions,
    COUNTIF(
      user_pseudo_id IS NULL
      OR user_pseudo_id = ''
      OR ga_session_id IS NULL
    ) AS events_without_full_session_key
  FROM
    window_events
  GROUP BY
    event_name
)
SELECT
  expected.step_order,
  expected.event_name,
  IFNULL(observed.event_count, 0) AS event_count,
  IFNULL(observed.distinct_users, 0) AS distinct_users,
  IFNULL(observed.distinct_sessions, 0) AS distinct_sessions,
  IFNULL(observed.events_without_full_session_key, 0) AS events_without_full_session_key
FROM
  expected_events AS expected
LEFT JOIN
  observed
ON
  observed.event_name = expected.event_name
ORDER BY
  expected.step_order;

-- ============================================================================
-- QUERY 2 - Presence per day (dense grid: every expected event x every clamp)
-- Grain    : one row per (event_date, expected event) - including zeros.
-- Why      : a step can exist for the window as a whole but be missing on a
--            single day (broken tag deploy, partial export). A dense grid
--            makes those gaps visible instead of letting them hide between
--            rows. CROSS JOIN builds the grid; LEFT JOIN fills it with counts.
-- Caveat   : the day list comes from the data itself - a day with no shard
--            never appears (00_project_settings.sql section C lists shards).
-- ============================================================================
WITH expected_events AS (
  SELECT 1 AS step_order, 'session_start' AS event_name
  UNION ALL SELECT 2, 'first_visit'
  UNION ALL SELECT 3, 'page_view'
  UNION ALL SELECT 4, 'view_item_list'
  UNION ALL SELECT 5, 'view_item'
  UNION ALL SELECT 6, 'add_to_cart'
  UNION ALL SELECT 7, 'remove_from_cart'
  UNION ALL SELECT 8, 'view_cart'
  UNION ALL SELECT 9, 'begin_checkout'
  UNION ALL SELECT 10, 'add_shipping_info'
  UNION ALL SELECT 11, 'add_payment_info'
  UNION ALL SELECT 12, 'purchase'
  UNION ALL SELECT 13, 'refund'
),
window_events AS (
  SELECT
    event_name,
    event_date
  FROM
    `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE
    event_name IN (SELECT event_name FROM expected_events)
    AND _TABLE_SUFFIX BETWEEN '20201101' AND '20201103' -- [WINDOW]
),
observed_daily AS (
  SELECT
    event_name,
    event_date,
    COUNT(*) AS event_count
  FROM
    window_events
  GROUP BY
    event_name,
    event_date
),
observed_days AS (
  SELECT DISTINCT
    event_date
  FROM
    window_events
),
grid AS (
  SELECT
    days.event_date,
    expected.step_order,
    expected.event_name
  FROM
    observed_days AS days
  CROSS JOIN
    expected_events AS expected
)
SELECT
  grid.event_date,
  grid.step_order,
  grid.event_name,
  IFNULL(observed_daily.event_count, 0) AS event_count
FROM
  grid
LEFT JOIN
  observed_daily
ON
  observed_daily.event_name = grid.event_name
  AND observed_daily.event_date = grid.event_date
ORDER BY
  grid.event_date,
  grid.step_order;
