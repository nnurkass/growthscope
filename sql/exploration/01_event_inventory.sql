-- ============================================================================
-- GROWTHSCOPE - Sprint 01 / Data Discovery (GA4 public sample ecommerce)
-- FILE      : 01_event_inventory.sql
-- PURPOSE   : Discover which event names actually exist in the window, how
--             often each occurs, and how each event fits a heuristic taxonomy
--             (funnel step / purchase / session boundary / acquisition / other).
--             Anything outside the expected event list is flagged for review.
-- TABLES    : `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
--             (daily sharded export tables, one table per day: events_YYYYMMDD)
-- SCAN RISK : LOW - reads the _TABLE_SUFFIX window (3 shards by default) and
--             projects only the columns actually used (event_name).
-- OUTPUT    : Q1: one row per distinct event_name.
--             Q2: one row per distinct event_name (boolean taxonomy flags).
--             Q3: one row per event_name NOT in the expected list.
-- CAVEATS   : - GA4 event names are implementation-defined, not schema-defined.
--               Custom tags can emit any name, so the inventory - not a
--               hardcoded assumption - is the source of truth.
--             - The taxonomy flags OVERLAP on purpose (e.g. `purchase` is both
--               a funnel step and a purchase event). Never add counts from two
--               flags together - you would double count.
--             - `event_name` values from this obfuscated sample may include
--               placeholder strings (`<Other>`, empty strings); treat any such
--               value as a data-quality signal, not as a real event.
-- READ-ONLY : SELECT statements only. No DDL/DML, no temp tables, no exports.
-- STATUS    : UNVERIFIED - BigQuery was not available in the build environment.
--             No results are reproduced here; run the file to produce them.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- WINDOW (single source of truth)
-- Default window : 2020-11-01 .. 2020-11-03 (3 days)
-- Predicate      : _TABLE_SUFFIX BETWEEN '20201101' AND '20201103'
-- To change      : edit the two date literals. Each query below contains that
--                  predicate exactly once, always in this exact form, so a
--                  find/replace of the two literals updates the whole file.
-- Why literals   : BigQuery prunes shards ONLY when the _TABLE_SUFFIX
--                  comparison is a constant expression - see section F of
--                  00_project_settings.sql.
-- Never          : do not replace this with a filter on `event_date` alone.
--                  `event_date` is a data column: filtering on it does NOT
--                  reduce the number of shards scanned (you would pay for the
--                  whole dataset). See 00_project_settings.sql.
-- ----------------------------------------------------------------------------

-- ============================================================================
-- QUERY 1 - Event inventory: which event names exist, how many, what share?
-- Grain    : one row per distinct event_name. No LIMIT on purpose - an
--            inventory with rows missing is not an inventory.
-- Expected : a small table (GA4 properties typically emit tens of distinct
--            names, not thousands). Column meanings:
--              event_name            - the GA4 event name
--              event_count           - number of event ROWS in the window
--              pct_of_window_events  - share of all events in the window (%)
--              count_rank            - rank by event_count (1 = most frequent)
-- ============================================================================
WITH window_events AS (
  -- Step 1: project ONLY event_name. The GA4 event tables are wide and
  -- columnar; reading one column is dramatically cheaper than `SELECT *`.
  -- The _TABLE_SUFFIX predicate restricts the wildcard to the 3 default
  -- shards. Without a CONSTANT filter here, every shard of the dataset
  -- (the sample covers ~3 months) would be scanned and billed.
  SELECT
    event_name
  FROM
    `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE
    _TABLE_SUFFIX BETWEEN '20201101' AND '20201103' -- [WINDOW]
),
event_counts AS (
  -- Step 2: collapse to one row per event name.
  SELECT
    event_name,
    COUNT(*) AS event_count
  FROM
    window_events
  GROUP BY
    event_name
)
-- Step 3: share of the window total.
-- The denominator is a window function over the ALREADY AGGREGATED CTE.
-- Why not `100 * COUNT(*) / (SELECT COUNT(*) FROM table)`: that scalar
-- subquery would scan the same data a second time and double the bill.
SELECT
  event_name,
  event_count,
  ROUND(100 * event_count / SUM(event_count) OVER (), 2) AS pct_of_window_events,
  RANK() OVER (ORDER BY event_count DESC) AS count_rank
FROM
  event_counts
ORDER BY
  event_count DESC;

-- ============================================================================
-- QUERY 2 - Heuristic taxonomy of event names
-- Grain    : one row per distinct event_name, plus 5 boolean flags.
-- Why      : GrowthScope needs to know which names are funnel steps before it
--            models a funnel. The flags below are PROJECT HEURISTICS, not GA4
--            facts - they encode our interpretation and must be reviewed.
--             - is_funnel_step      : browsing -> checkout -> purchase path
--             - is_purchase         : ecommerce transaction events
--                                     (purchase, refund - refund is the
--                                     reverse ecommerce event)
--             - is_session_boundary : events that open a session or mark the
--                                     first-ever visit
--             - is_acquisition      : events that carry traffic-source
--                                     attribution (GA4 attaches source,
--                                     medium, campaign, gclid ... to these;
--                                     04_event_parameters.sql measures which
--                                     events actually carry them here)
--             - is_other            : none of the above - needs review
-- Warning  : the flags are NOT mutually exclusive. To build exclusive groups,
--            pick one label with a CASE expression - never SUM() two flags.
-- ============================================================================
WITH window_events AS (
  SELECT
    event_name
  FROM
    `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE
    _TABLE_SUFFIX BETWEEN '20201101' AND '20201103' -- [WINDOW]
),
event_counts AS (
  SELECT
    event_name,
    COUNT(*) AS event_count
  FROM
    window_events
  GROUP BY
    event_name
),
classified AS (
  SELECT
    event_name,
    event_count,
    event_name IN (
      'page_view',
      'view_item_list',
      'view_item',
      'add_to_cart',
      'remove_from_cart',
      'view_cart',
      'begin_checkout',
      'add_shipping_info',
      'add_payment_info',
      'purchase'
    ) AS is_funnel_step,
    event_name IN ('purchase', 'refund') AS is_purchase,
    event_name IN ('session_start', 'first_visit') AS is_session_boundary,
    event_name IN ('session_start', 'first_visit') AS is_acquisition
  FROM
    event_counts
),
flagged AS (
  -- `is_other` is computed in a separate CTE because a SELECT clause cannot
  -- reference aliases defined in the same SELECT list.
  SELECT
    event_name,
    event_count,
    is_funnel_step,
    is_purchase,
    is_session_boundary,
    is_acquisition,
    NOT (is_funnel_step OR is_purchase OR is_session_boundary OR is_acquisition) AS is_other
  FROM
    classified
)
SELECT
  event_name,
  event_count,
  is_funnel_step,
  is_purchase,
  is_session_boundary,
  is_acquisition,
  is_other
FROM
  flagged
ORDER BY
  event_count DESC;

-- ============================================================================
-- QUERY 3 - Unexpected event names (not in the GrowthScope expected list)
-- Grain    : one row per event_name outside the expected list.
-- Why      : GA4 automatically collects extra events (e.g. scroll, click,
--            user_engagement, form interactions, file downloads, video events
--            via Enhanced Measurement - which the Google Merchandise Store
--            sample uses) and implementers add custom ones. They are usually
--            NOT errors - but GrowthScope must consciously decide whether any
--            of them is relevant. Anything here needs a reviewed decision.
-- Note     : the expected list is exactly the 13 events audited in
--            05_funnel_event_audit.sql, so the two files stay consistent.
-- ============================================================================
WITH window_events AS (
  SELECT
    event_name
  FROM
    `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE
    _TABLE_SUFFIX BETWEEN '20201101' AND '20201103' -- [WINDOW]
),
event_counts AS (
  SELECT
    event_name,
    COUNT(*) AS event_count
  FROM
    window_events
  GROUP BY
    event_name
)
SELECT
  event_name,
  event_count
FROM
  event_counts
WHERE
  event_name NOT IN (
    'session_start',
    'first_visit',
    'page_view',
    'view_item_list',
    'view_item',
    'add_to_cart',
    'remove_from_cart',
    'view_cart',
    'begin_checkout',
    'add_shipping_info',
    'add_payment_info',
    'purchase',
    'refund'
  )
ORDER BY
  event_count DESC;
