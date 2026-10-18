-- ============================================================================
-- GROWTHSCOPE - Sprint 01 / Data Discovery (GA4 public sample ecommerce)
-- FILE      : 06_purchase_revenue_audit.sql
-- PURPOSE   : Audit the purchase event and every field GrowthScope could sum
--             as revenue, BEFORE any revenue number is produced:
--               Q1 - transaction identity: how many purchases are there, how
--                    many carry a usable transaction_id, how many do not?
--               Q2 - revenue field availability: purchase_revenue vs
--                    purchase_revenue_in_usd vs event_value_in_usd
--               Q3 - which currency values appear on purchases
--               Q4 - item-level availability: items array, price, quantity
--               Q5 - duplicate transaction_id risk: the same transaction
--                    recorded more than once
-- TABLES    : `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
-- SCAN RISK : MEDIUM - only purchase events qualify, but the filter still
--             reads the event_name column of every row in the 3 shards, and
--             the ecommerce RECORD + items array are projected. Purchase
--             volume is small relative to traffic; the scan is bounded by the
--             3-day window. Dry-run before widening (see file 00).
-- OUTPUT    : Q1: one row (transaction identity summary).
--             Q2: one row (revenue field availability summary).
--             Q3: one row per currency value observed on purchases.
--             Q4: one row (purchase-level + item-level counters combined).
--             Q5: one row per duplicated transaction_id (capped at 100).
-- CAVEATS   : - DUPLICATE TRANSACTIONS ARE EXPECTED. The same purchase can
--               arrive more than once: client-side gtag + server-side
--               Measurement Protocol, a retried/double-fired tag, the buyer
--               completing the same order on two devices, or backfilled
--               uploads. The GA4 interface de-duplicates a transaction per
--               user for you; the raw export does NOT. Q5 must be read BEFORE
--               any SUM() of revenue - otherwise the same money is counted
--               twice.
--             - `purchase_revenue` is the revenue in the STORE's currency and
--               `purchase_revenue_in_usd` is the same revenue in USD. They are
--               two fields with two units, not two names for one value.
--               The REAL currency trap is therefore mixing units: summing
--               `purchase_revenue` across events whose currencies differ adds
--               dollars to euros. `purchase_revenue_in_usd` is always USD and is
--               therefore always safe to sum. Q3 establishes which currencies
--               actually appear in the window.
--               A separate claim - that `purchase_revenue` is NULL specifically
--               when the event currency differs from the property currency - is
--               NOT supported by the documentation reviewed for this project (see
--               docs/dataset_research.md, section 10.2, marked [UNRESOLVED]).
--               Do NOT design around it. Q2 measures the NULL rate empirically;
--               if an asymmetry appears, report it as an observed finding.

--             - `event_value_in_usd` (top-level column) is a currency-
--               normalized event value. For purchase events it usually equals
--               purchase_revenue_in_usd, but that is an assumption - Q2
--               counts how often each field is populated.
--             - REFUNDS ARE NOT SUBTRACTED here. A refund event links back to
--               its transaction via transaction_id; net revenue is a Sprint 02
--               modelling decision, not a discovery query.
--             - The obfuscated sample can contain placeholder values (NULL,
--               '', `<Other>`); '' is treated as missing everywhere below.
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
-- QUERY 1 - Transaction identity: can purchases be de-duplicated at all?
-- Grain    : one row.
-- Why      : transaction_id is the only key that survives across users and
--            devices. If it is missing, duplicates cannot be detected and
--            revenue cannot be corrected - so its coverage is measured first.
-- Columns  :
--   purchase_events              - purchase rows in the window
--   events_missing_transaction_id- NULL or '' transaction_id
--   pct_missing_transaction_id   - share of purchase_events (%)
--   distinct_transaction_ids     - non-empty transaction ids seen
--   distinct_users               - distinct user_pseudo_id on purchases
--   avg_rows_per_transaction     - non-empty purchase rows / distinct ids;
--                                  a value noticeably above 1 means the same
--                                  transaction appears multiple times (Q5)
-- ============================================================================
WITH purchase_events AS (
  -- `ecommerce.transaction_id` is the canonical location; a
  -- `transaction_id` parameter can also exist inside event_params (file 04
  -- shows parameter coverage). Only the RECORD field is audited here.
  SELECT
    user_pseudo_id,
    ecommerce.transaction_id AS transaction_id
  FROM
    `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE
    event_name = 'purchase'
    AND _TABLE_SUFFIX BETWEEN '20201101' AND '20201103' -- [WINDOW]
)
SELECT
  COUNT(*) AS purchase_events,
  COUNTIF(transaction_id IS NULL OR transaction_id = '') AS events_missing_transaction_id,
  ROUND(
    100 * SAFE_DIVIDE(
      COUNTIF(transaction_id IS NULL OR transaction_id = ''),
      COUNT(*)
    ),
    3
  ) AS pct_missing_transaction_id,
  COUNT(
    DISTINCT IF(
      transaction_id IS NOT NULL AND transaction_id != '',
      transaction_id,
      NULL
    )
  ) AS distinct_transaction_ids,
  COUNT(DISTINCT user_pseudo_id) AS distinct_users,
  ROUND(
    SAFE_DIVIDE(
      COUNTIF(transaction_id IS NOT NULL AND transaction_id != ''),
      COUNT(
        DISTINCT IF(
          transaction_id IS NOT NULL AND transaction_id != '',
          transaction_id,
          NULL
        )
      )
    ),
    3
  ) AS avg_rows_per_transaction
FROM
  purchase_events;

-- ============================================================================
-- QUERY 2 - Revenue field availability (which field can be trusted?)
-- Grain    : one row.
-- Why      : "purchase_revenue exists" is an assumption. This counts how
--            often each candidate revenue field is actually populated, and
--            separates three NULL patterns that have three different causes.
-- Columns  :
--   purchase_events                     - purchase rows in the window
--   with_purchase_revenue               - ecommerce.purchase_revenue non-null
--   with_purchase_revenue_in_usd        - ecommerce.purchase_revenue_in_usd
--                                         non-null
--   with_event_value_in_usd             - top-level event_value_in_usd
--                                         non-null
--   pct_with_purchase_revenue[_in_usd]  - coverage shares (%)
--   pct_with_event_value_in_usd         - coverage share (%)
--   store_currency_null_usd_present     - purchase_revenue NULL while
--                                         purchase_revenue_in_usd is present.
--                                         This is the EMPIRICAL test of the
--                                         "event currency != property currency"
--                                         claim, which the documentation review
--                                         could NOT confirm (marked [UNRESOLVED]
--                                         in docs/dataset_research.md 10.2).
--                                         If the count is 0, the claim is not
--                                         observable here and must not be
--                                         asserted anywhere. If it is non-zero,
--                                         report it as an OBSERVED finding with
--                                         this query as its evidence - never as
--                                         documented behaviour.
--   usd_only_in_event_value             - both ecommerce revenue fields NULL
--                                         but event_value_in_usd present
--   no_revenue_signal                   - all three fields NULL: the purchase
--                                         row carries no money at all
-- ============================================================================
WITH purchase_events AS (
  SELECT
    ecommerce.purchase_revenue AS purchase_revenue,
    ecommerce.purchase_revenue_in_usd AS purchase_revenue_in_usd,
    event_value_in_usd AS event_value_in_usd
  FROM
    `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE
    event_name = 'purchase'
    AND _TABLE_SUFFIX BETWEEN '20201101' AND '20201103' -- [WINDOW]
)
SELECT
  COUNT(*) AS purchase_events,
  COUNTIF(purchase_revenue IS NOT NULL) AS with_purchase_revenue,
  COUNTIF(purchase_revenue_in_usd IS NOT NULL) AS with_purchase_revenue_in_usd,
  COUNTIF(event_value_in_usd IS NOT NULL) AS with_event_value_in_usd,
  ROUND(
    100 * SAFE_DIVIDE(COUNTIF(purchase_revenue IS NOT NULL), COUNT(*)),
    3
  ) AS pct_with_purchase_revenue,
  ROUND(
    100 * SAFE_DIVIDE(COUNTIF(purchase_revenue_in_usd IS NOT NULL), COUNT(*)),
    3
  ) AS pct_with_purchase_revenue_in_usd,
  ROUND(
    100 * SAFE_DIVIDE(COUNTIF(event_value_in_usd IS NOT NULL), COUNT(*)),
    3
  ) AS pct_with_event_value_in_usd,
  COUNTIF(
    purchase_revenue IS NULL
    AND purchase_revenue_in_usd IS NOT NULL
  ) AS store_currency_null_usd_present,
  COUNTIF(
    purchase_revenue IS NULL
    AND purchase_revenue_in_usd IS NULL
    AND event_value_in_usd IS NOT NULL
  ) AS usd_only_in_event_value,
  COUNTIF(
    purchase_revenue IS NULL
    AND purchase_revenue_in_usd IS NULL
    AND event_value_in_usd IS NULL
  ) AS no_revenue_signal
FROM
  purchase_events;

-- ============================================================================
-- QUERY 3 - Currency values on purchase events
-- Grain    : one row per distinct transaction currency (missing -> one
--            '(missing)' row).
-- Why      : amounts in different currencies are different units. This lists
--            exactly which units exist in the window before anything is
--            summed, and how much of the purchase volume sits in each.
-- Method   : the transaction currency is an `event_params` key, NOT a field of
--            the `ecommerce` RECORD. The record exposes transaction_id,
--            purchase_revenue(_in_usd), total_item_quantity, unique_items and the
--            tax/shipping/refund values - but no currency column. Reading
--            `ecommerce.currency` would fail to resolve. The correlated scalar
--            subquery below reads `currency` without fanning out the rows.
-- Columns  :
--   currency               - event_params['currency'] ('(missing)' for NULL/'')
--   purchase_events        - purchase rows in that currency
--   pct_of_purchases       - share of all purchase rows (%)
--   distinct_users         - distinct user_pseudo_id in that currency
--   distinct_transaction_ids - non-empty transaction ids in that currency
-- ============================================================================
WITH purchase_events AS (
  SELECT
    user_pseudo_id,
    (
      SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'currency'
    ) AS currency,
    ecommerce.transaction_id AS transaction_id
  FROM
    `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE
    event_name = 'purchase'
    AND _TABLE_SUFFIX BETWEEN '20201101' AND '20201103' -- [WINDOW]
)
SELECT
  IF(currency IS NULL OR currency = '', '(missing)', currency) AS currency,
  COUNT(*) AS purchase_events,
  ROUND(100 * SAFE_DIVIDE(COUNT(*), SUM(COUNT(*)) OVER ()), 3) AS pct_of_purchases,
  COUNT(DISTINCT user_pseudo_id) AS distinct_users,
  COUNT(
    DISTINCT IF(
      transaction_id IS NOT NULL AND transaction_id != '',
      transaction_id,
      NULL
    )
  ) AS distinct_transaction_ids
FROM
  purchase_events
GROUP BY
  currency
ORDER BY
  purchase_events DESC;

-- ============================================================================
-- QUERY 4 - Item-level availability (items array, price, quantity)
-- Grain    : one row - purchase-level counters CROSS JOINed with item-level
--            counters. Full-market-basket revenue needs the item grain, so
--            its completeness is audited separately from the event grain.
-- Method   : purchase-level counters are aggregates over purchase events;
--            item-level counters are aggregates over the flattened items
--            array (CROSS JOIN UNNEST). Both are single-row results, so the
--            CROSS JOIN combines them 1 x 1 without fan-out.
-- Columns  :
--   purchase_events              - purchase rows in the window
--   events_with_items_array      - rows where items is present and non-empty
--   item_rows                    - total item lines across all purchases
--   distinct_item_ids            - non-empty item_id values
--   items_missing_item_id        - NULL or '' item_id
--   items_missing_item_name      - NULL or '' item_name
--   items_missing_quantity       - NULL quantity
--   items_nonpositive_quantity   - quantity <= 0 (suspicious for a purchase)
--   items_missing_price          - NULL store-currency price
--   items_missing_price_in_usd   - NULL USD price
--   items_with_no_monetary_value - both price fields NULL
-- ============================================================================
WITH purchase_events AS (
  SELECT
    items
  FROM
    `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE
    event_name = 'purchase'
    AND _TABLE_SUFFIX BETWEEN '20201101' AND '20201103' -- [WINDOW]
),
item_rows AS (
  -- Flattening to item grain is intentional here: every counter below counts
  -- ITEM LINES, not events. The fan-out that would corrupt event-level counts
  -- is the point of this CTE. `items` carries its own item_params array, not
  -- queried here.
  SELECT
    item.item_id AS item_id,
    item.item_name AS item_name,
    item.quantity AS quantity,
    item.price AS price,
    item.price_in_usd AS price_in_usd
  FROM
    purchase_events
  CROSS JOIN
    UNNEST(purchase_events.items) AS item
),
purchase_level AS (
  SELECT
    COUNT(*) AS purchase_events,
    COUNTIF(
      items IS NOT NULL AND ARRAY_LENGTH(items) > 0
    ) AS events_with_items_array
  FROM
    purchase_events
),
item_level AS (
  SELECT
    COUNT(*) AS item_rows,
    COUNT(
      DISTINCT IF(
        item_id IS NOT NULL AND item_id != '',
        item_id,
        NULL
      )
    ) AS distinct_item_ids,
    COUNTIF(item_id IS NULL OR item_id = '') AS items_missing_item_id,
    COUNTIF(item_name IS NULL OR item_name = '') AS items_missing_item_name,
    COUNTIF(quantity IS NULL) AS items_missing_quantity,
    COUNTIF(quantity IS NOT NULL AND quantity <= 0) AS items_nonpositive_quantity,
    COUNTIF(price IS NULL) AS items_missing_price,
    COUNTIF(price_in_usd IS NULL) AS items_missing_price_in_usd,
    COUNTIF(
      price IS NULL AND price_in_usd IS NULL
    ) AS items_with_no_monetary_value
  FROM
    item_rows
)
SELECT
  purchase_level.purchase_events,
  purchase_level.events_with_items_array,
  item_level.item_rows,
  item_level.distinct_item_ids,
  item_level.items_missing_item_id,
  item_level.items_missing_item_name,
  item_level.items_missing_quantity,
  item_level.items_nonpositive_quantity,
  item_level.items_missing_price,
  item_level.items_missing_price_in_usd,
  item_level.items_with_no_monetary_value
FROM
  purchase_level
CROSS JOIN
  item_level;

-- ============================================================================
-- QUERY 5 - Duplicate transaction_id risk (READ BEFORE SUMMING REVENUE)
-- Grain    : one row per transaction_id with more than one purchase row
--            (display capped at 100 rows, worst first).
-- Why      : a naive SUM(purchase_revenue) over raw rows double-counts every
--            duplicated transaction. This query surfaces exactly which
--            transactions repeat and how their revenue rows relate.
-- Columns  :
--   transaction_id               - the duplicated transaction
--   purchase_rows                - how many purchase rows carry that id
--   distinct_users               - distinct user_pseudo_id across the rows
--   distinct_sessions            - distinct composite session keys
--                                  (user_pseudo_id | ga_session_id)
--   first_seen / last_seen       - event_timestamp range (UTC)
--   min_row_revenue_in_usd /
--   max_row_revenue_in_usd       - range of the per-row USD amounts
--   summed_revenue_in_usd        - what a naive SUM() would produce
-- Reading it:
--   - min == max on all duplicate rows  -> looks like an EXACT retry; the
--     real revenue is ONE row (use max, not sum).
--   - rows differ (e.g. partially captured amounts) -> the correct net value
--     must be decided deliberately (usually the MAX row, since GA4 re-sends
--     the full transaction on update) - do not guess in discovery.
--   - distinct_users > 1 -> the same order appears on two devices/identities;
--     transaction_id, not user_pseudo_id, is the only safe de-duplication key.
-- Caveat   : NO ROWS RETURNED means no duplicate was found IN THIS WINDOW -
--            it is not proof that the production data is clean. Production
--            aggregation must still de-duplicate by transaction_id.
-- ============================================================================
WITH purchase_events AS (
  SELECT
    ecommerce.transaction_id AS transaction_id,
    user_pseudo_id,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS ga_session_id,
    event_timestamp,
    ecommerce.purchase_revenue_in_usd AS purchase_revenue_in_usd
  FROM
    `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE
    event_name = 'purchase'
    AND _TABLE_SUFFIX BETWEEN '20201101' AND '20201103' -- [WINDOW]
),
valid_transactions AS (
  -- Rows without a usable transaction_id cannot be de-duplicated; they are
  -- counted in Q1 and deliberately excluded from this duplicate audit.
  SELECT
    transaction_id,
    user_pseudo_id,
    ga_session_id,
    event_timestamp,
    purchase_revenue_in_usd
  FROM
    purchase_events
  WHERE
    transaction_id IS NOT NULL
    AND transaction_id != ''
),
per_transaction AS (
  SELECT
    transaction_id,
    COUNT(*) AS purchase_rows,
    COUNT(DISTINCT user_pseudo_id) AS distinct_users,
    COUNT(
      DISTINCT IF(
        user_pseudo_id IS NOT NULL
        AND user_pseudo_id != ''
        AND ga_session_id IS NOT NULL,
        CONCAT(user_pseudo_id, '|', CAST(ga_session_id AS STRING)),
        NULL
      )
    ) AS distinct_sessions,
    MIN(TIMESTAMP_MICROS(event_timestamp)) AS first_seen,
    MAX(TIMESTAMP_MICROS(event_timestamp)) AS last_seen,
    ROUND(MIN(purchase_revenue_in_usd), 2) AS min_row_revenue_in_usd,
    ROUND(MAX(purchase_revenue_in_usd), 2) AS max_row_revenue_in_usd,
    ROUND(SUM(purchase_revenue_in_usd), 2) AS summed_revenue_in_usd
  FROM
    valid_transactions
  GROUP BY
    transaction_id
)
SELECT
  transaction_id,
  purchase_rows,
  distinct_users,
  distinct_sessions,
  first_seen,
  last_seen,
  min_row_revenue_in_usd,
  max_row_revenue_in_usd,
  summed_revenue_in_usd
FROM
  per_transaction
WHERE
  purchase_rows > 1
ORDER BY
  purchase_rows DESC,
  summed_revenue_in_usd DESC
LIMIT 100;
