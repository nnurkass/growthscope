-- ============================================================================
-- GROWTHSCOPE - Sprint 01 / Data Discovery (GA4 public sample ecommerce)
-- FILE      : 07_session_feasibility.sql
-- PURPOSE   : Decide whether the export supports the SESSION grain that every
--             funnel model in Sprint 02 depends on:
--               Q1 - how many events carry a usable ga_session_id at all?
--               Q2 - composite session key proof: user_pseudo_id |
--                    ga_session_id vs ga_session_id alone
--               Q3 - raw ga_session_id values shared by several users
--                    (the evidence behind the composite key)
--               Q4 - events per session and observed session duration
--               Q5 - does every observed session have exactly one
--                    session_start marker inside the window?
--               Q6 - do sessions cross midnight (multiple event_date values)?
-- TABLES    : `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
-- SCAN RISK : MEDIUM - the window's shards are read and ga_session_id is
--             extracted from event_params per event. Bounded to 3 days;
--             dry-run before widening (see file 00).
-- OUTPUT    : Q1: one row. Q2: one row. Q3: one row per colliding
--             ga_session_id (capped at 100). Q4: one row. Q5: one row.
--             Q6: one row.
-- CAVEATS   : - WHAT A GA4 SESSION IS (per Google Analytics documentation,
--               https://support.google.com/analytics/answer/9191807):
--               a session begins with a session_start event and expires after
--               30 minutes of inactivity; a change of campaign/medium also
--               starts a new session. The timeout is configurable, so treat
--               "30 min" as the default, not a constant of the dataset.
--             - `ga_session_id` is the SESSION-START TIMESTAMP IN SECONDS
--               (not a sequential id). Two sessions that start in the same
--               second - even for different users - share the value. Grouping
--               by ga_session_id alone therefore merges unrelated users'
--               sessions. The ONLY safe key is
--               (user_pseudo_id | ga_session_id). Q2/Q3 prove this on data
--               instead of assuming it.
--             - Events missing user_pseudo_id or ga_session_id cannot be
--               attributed to a session. Q1 measures how much of the window
--               falls outside the session grain.
--             - WINDOW SPLICE: this 3-day window cuts a continuous event
--               stream. Sessions that started before 2020-11-01 appear without
--               their session_start event; sessions near the end are truncated
--               and keep generating events after the window. Edge effects are
--               expected - Q5 quantifies them rather than hiding them.
--             - A session can be counted on two event_date values if it
--               crosses midnight (Q6 measures how often). Summing daily
--               session counts therefore overcounts. Session-scoped reporting
--               usually attributes a session to its start date - verify
--               against GA4 documentation before Sprint 02 modelling.
--             - "Sessions" in this file are sessions OBSERVED INSIDE THE
--               WINDOW from events with a full composite key - not the
--               session numbers shown in the GA4 interface.
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
-- QUERY 1 - ga_session_id availability
-- Grain    : one row.
-- Why      : the session grain is only usable where both halves of the
--            composite key exist. This is the coverage ceiling for every
--            session-level metric in Sprint 02.
-- Columns  :
--   total_events                    - event rows in the window
--   events_with_ga_session_id       - ga_session_id parameter present
--   events_missing_ga_session_id    - parameter absent (NULL)
--   pct_missing_ga_session_id       - share of total_events (%)
--   events_without_user_pseudo_id   - user_pseudo_id NULL or ''
--   events_with_full_session_key    - both halves present: the only rows a
--                                     session model can use
-- ============================================================================
WITH window_events AS (
  -- One extraction, one pass: keep the correlated scalar subquery so counts
  -- stay at event grain (see the extraction note in 04_event_parameters.sql).
  SELECT
    user_pseudo_id,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS ga_session_id
  FROM
    `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE
    _TABLE_SUFFIX BETWEEN '20201101' AND '20201103' -- [WINDOW]
)
SELECT
  COUNT(*) AS total_events,
  COUNTIF(ga_session_id IS NOT NULL) AS events_with_ga_session_id,
  COUNTIF(ga_session_id IS NULL) AS events_missing_ga_session_id,
  ROUND(100 * SAFE_DIVIDE(COUNTIF(ga_session_id IS NULL), COUNT(*)), 3) AS pct_missing_ga_session_id,
  COUNTIF(user_pseudo_id IS NULL OR user_pseudo_id = '') AS events_without_user_pseudo_id,
  COUNTIF(
    user_pseudo_id IS NOT NULL
    AND user_pseudo_id != ''
    AND ga_session_id IS NOT NULL
  ) AS events_with_full_session_key
FROM
  window_events;

-- ============================================================================
-- QUERY 2 - Composite key proof: would ga_session_id alone lose sessions?
-- Grain    : one row.
-- Why      : this is the decisive measurement. If distinct_composite_keys is
--            greater than distinct_ga_session_ids, some ga_session_id values
--            are shared across users and the composite key is NOT optional.
-- Columns  :
--   distinct_users_with_session_events - users contributing session-keyed rows
--   distinct_ga_session_ids            - raw id values seen
--   distinct_composite_keys            - distinct (user_pseudo_id |
--                                        ga_session_id) pairs: the true
--                                        session count in the window
--   sessions_lost_if_id_used_alone     - composite keys minus raw ids; the
--                                        number of sessions that vanish if
--                                        you group by ga_session_id alone
-- ============================================================================
WITH window_events AS (
  SELECT
    user_pseudo_id,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS ga_session_id
  FROM
    `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE
    _TABLE_SUFFIX BETWEEN '20201101' AND '20201103' -- [WINDOW]
),
session_keyed AS (
  SELECT
    user_pseudo_id,
    ga_session_id
  FROM
    window_events
  WHERE
    user_pseudo_id IS NOT NULL
    AND user_pseudo_id != ''
    AND ga_session_id IS NOT NULL
)
SELECT
  COUNT(DISTINCT user_pseudo_id) AS distinct_users_with_session_events,
  COUNT(DISTINCT ga_session_id) AS distinct_ga_session_ids,
  COUNT(
    DISTINCT CONCAT(user_pseudo_id, '|', CAST(ga_session_id AS STRING))
  ) AS distinct_composite_keys,
  COUNT(
    DISTINCT CONCAT(user_pseudo_id, '|', CAST(ga_session_id AS STRING))
  ) - COUNT(DISTINCT ga_session_id) AS sessions_lost_if_id_used_alone
FROM
  session_keyed;

-- ============================================================================
-- QUERY 3 - Raw ga_session_id values shared by more than one user
-- Grain    : one row per colliding ga_session_id (display capped at 100,
--            worst first).
-- Why      : Q2 gives a number; this query shows the mechanism. Because
--            ga_session_id is the session-start timestamp in seconds, any two
--            users starting a session in the same second collide.
-- Columns  :
--   ga_session_id             - the shared id value
--   distinct_users_sharing_id - how many different users used that value
--   session_start_ts_utc      - the id rendered as a timestamp (what the
--                               number actually means; seconds -> UTC)
-- ============================================================================
WITH window_events AS (
  SELECT
    user_pseudo_id,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS ga_session_id
  FROM
    `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE
    _TABLE_SUFFIX BETWEEN '20201101' AND '20201103' -- [WINDOW]
),
session_keyed AS (
  SELECT
    user_pseudo_id,
    ga_session_id
  FROM
    window_events
  WHERE
    user_pseudo_id IS NOT NULL
    AND user_pseudo_id != ''
    AND ga_session_id IS NOT NULL
),
collisions AS (
  SELECT
    ga_session_id,
    COUNT(DISTINCT user_pseudo_id) AS distinct_users_sharing_id
  FROM
    session_keyed
  GROUP BY
    ga_session_id
  HAVING
    COUNT(DISTINCT user_pseudo_id) > 1
)
SELECT
  ga_session_id,
  distinct_users_sharing_id,
  TIMESTAMP_SECONDS(ga_session_id) AS session_start_ts_utc
FROM
  collisions
ORDER BY
  distinct_users_sharing_id DESC,
  ga_session_id
LIMIT 100;

-- ============================================================================
-- QUERY 4 - Events per session and observed session duration
-- Grain    : one row.
-- Why      : funnel modelling needs to know how many events a session
--            contains. A population of single-event sessions, for example,
--            caps how much journey detail any funnel can ever show.
-- Columns  :
--   sessions                  - composite-key sessions in the window
--   min_events_per_session    - smallest event count in a session
--   avg_events_per_session    - mean event count
--   max_events_per_session    - largest event count
--   p50 / p90 / p99_events_per_session - approximate quantiles of the
--                               event-count distribution
--   single_event_sessions     - sessions with exactly one event
--   pct_single_event_sessions - share of sessions (%)
--   min / avg / max_observed_duration_seconds - time between the FIRST and
--                               LAST event of a session (NOT the GA4 session
--                               duration: a session with one event has zero
--                               observed duration, and inactivity time after
--                               the last event is invisible)
-- ============================================================================
WITH window_events AS (
  SELECT
    user_pseudo_id,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS ga_session_id,
    event_timestamp
  FROM
    `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE
    _TABLE_SUFFIX BETWEEN '20201101' AND '20201103' -- [WINDOW]
),
sessions AS (
  SELECT
    user_pseudo_id,
    ga_session_id,
    COUNT(*) AS events_in_session,
    MAX(event_timestamp) - MIN(event_timestamp) AS observed_duration_micros
  FROM
    window_events
  WHERE
    user_pseudo_id IS NOT NULL
    AND user_pseudo_id != ''
    AND ga_session_id IS NOT NULL
  GROUP BY
    user_pseudo_id,
    ga_session_id
)
SELECT
  COUNT(*) AS sessions,
  MIN(events_in_session) AS min_events_per_session,
  ROUND(AVG(events_in_session), 2) AS avg_events_per_session,
  MAX(events_in_session) AS max_events_per_session,
  APPROX_QUANTILES(events_in_session, 100)[OFFSET(50)] AS p50_events_per_session,
  APPROX_QUANTILES(events_in_session, 100)[OFFSET(90)] AS p90_events_per_session,
  APPROX_QUANTILES(events_in_session, 100)[OFFSET(99)] AS p99_events_per_session,
  COUNTIF(events_in_session = 1) AS single_event_sessions,
  ROUND(100 * SAFE_DIVIDE(COUNTIF(events_in_session = 1), COUNT(*)), 2) AS pct_single_event_sessions,
  ROUND(MIN(observed_duration_micros) / 1000000, 1) AS min_observed_duration_seconds,
  ROUND(AVG(observed_duration_micros) / 1000000, 1) AS avg_observed_duration_seconds,
  ROUND(MAX(observed_duration_micros) / 1000000, 1) AS max_observed_duration_seconds
FROM
  sessions;

-- ============================================================================
-- QUERY 5 - session_start marker presence per observed session
-- Grain    : one row.
-- Why      : every GA4 session is supposed to open with exactly one
--            session_start event. Zero markers means the session began before
--            the window opened (expected at the edge, a problem in the
--            middle); MORE THAN ONE marker for the same composite key would
--            indicate duplicate ingestion and must be investigated.
-- Columns  :
--   observed_sessions                  - composite-key sessions in the window
--   sessions_with_exactly_one_start    - exactly one session_start event
--   sessions_missing_start_marker      - zero session_start events seen
--   sessions_with_multiple_starts      - more than one (anomaly signal)
--   pct_missing_start_marker           - share of observed_sessions (%)
-- ============================================================================
WITH window_events AS (
  SELECT
    user_pseudo_id,
    event_name,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS ga_session_id
  FROM
    `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE
    _TABLE_SUFFIX BETWEEN '20201101' AND '20201103' -- [WINDOW]
),
sessions AS (
  SELECT DISTINCT
    user_pseudo_id,
    ga_session_id
  FROM
    window_events
  WHERE
    user_pseudo_id IS NOT NULL
    AND user_pseudo_id != ''
    AND ga_session_id IS NOT NULL
),
start_markers AS (
  SELECT
    user_pseudo_id,
    ga_session_id,
    COUNT(*) AS session_start_events
  FROM
    window_events
  WHERE
    event_name = 'session_start'
    AND user_pseudo_id IS NOT NULL
    AND user_pseudo_id != ''
    AND ga_session_id IS NOT NULL
  GROUP BY
    user_pseudo_id,
    ga_session_id
),
joined AS (
  SELECT
    sessions.user_pseudo_id,
    sessions.ga_session_id,
    IFNULL(start_markers.session_start_events, 0) AS session_start_events
  FROM
    sessions
  LEFT JOIN
    start_markers
  ON
    start_markers.user_pseudo_id = sessions.user_pseudo_id
    AND start_markers.ga_session_id = sessions.ga_session_id
)
SELECT
  COUNT(*) AS observed_sessions,
  COUNTIF(session_start_events = 1) AS sessions_with_exactly_one_start,
  COUNTIF(session_start_events = 0) AS sessions_missing_start_marker,
  COUNTIF(session_start_events > 1) AS sessions_with_multiple_starts,
  ROUND(100 * SAFE_DIVIDE(COUNTIF(session_start_events = 0), COUNT(*)), 2) AS pct_missing_start_marker
FROM
  joined;

-- ============================================================================
-- QUERY 6 - Sessions crossing midnight (multiple event_date values)
-- Grain    : one row.
-- Why      : `event_date` is the date of each EVENT, while a session is one
--            continuous visit. A session that crosses midnight therefore
--            appears under two event_date values, and summing per-day session
--            counts overcounts. This measures how large that effect is in the
--            window before any daily session metric is published.
-- Columns  :
--   observed_sessions              - composite-key sessions in the window
--   sessions_spanning_multiple_dates - sessions with events on >1 event_date
--   pct_spanning_multiple_dates    - share of observed_sessions (%)
--   max_distinct_dates_per_session - worst case observed
-- Note     : because this window starts at 2020-11-01, sessions cut by the
--            window edge also count here; the number is an upper bound of the
--            midnight effect.
-- ============================================================================
WITH window_events AS (
  SELECT
    user_pseudo_id,
    event_date,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS ga_session_id
  FROM
    `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE
    _TABLE_SUFFIX BETWEEN '20201101' AND '20201103' -- [WINDOW]
),
per_session AS (
  SELECT
    user_pseudo_id,
    ga_session_id,
    COUNT(DISTINCT event_date) AS distinct_event_dates
  FROM
    window_events
  WHERE
    user_pseudo_id IS NOT NULL
    AND user_pseudo_id != ''
    AND ga_session_id IS NOT NULL
  GROUP BY
    user_pseudo_id,
    ga_session_id
)
SELECT
  COUNT(*) AS observed_sessions,
  COUNTIF(distinct_event_dates > 1) AS sessions_spanning_multiple_dates,
  ROUND(100 * SAFE_DIVIDE(COUNTIF(distinct_event_dates > 1), COUNT(*)), 2) AS pct_spanning_multiple_dates,
  MAX(distinct_event_dates) AS max_distinct_dates_per_session
FROM
  per_session;
