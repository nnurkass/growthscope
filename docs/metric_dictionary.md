# GrowthScope — Metric Dictionary

Every business metric GrowthScope intends to publish, with an explicit formula, its numerator and denominator in words, its aggregation level, required data fields, known failure modes, and a validation status.

Formulas below are written so they can be implemented directly in SQL (Sprint 02+) and mirrored in pandas checks.

## Validation status vocabulary

| Status | Meaning |
|---|---|
| `PROPOSED` | Definition agreed and documented; **not implemented** anywhere yet. |
| `IMPLEMENTED (LOCAL)` | Logic exists and is unit-tested locally against synthetic fixtures. **Not a business validation.** |
| `VERIFIED (LIVE)` | Computed against the real dataset and cross-checked (e.g. against an independent query or aggregation). |
| `BLOCKED (NO BIGQUERY ACCESS)` | Cannot be validated in this environment — no credentials, no query execution. |

> [!WARNING]
> **Status at the end of Sprint 01: every business metric in this document is `PROPOSED` and `BLOCKED (NO BIGQUERY ACCESS)` — none is `VERIFIED (LIVE)`, none is reliable for decision-making yet.** The only locally checked properties are structural invariants of the *definitions* (e.g. funnel step counts must be monotonically non-increasing by construction), unit-tested on synthetic fixtures with `IMPLEMENTED (LOCAL)` logic. Those checks validate arithmetic, not reality. Live verification is the first task of Sprint 02.

## Conventions used in all formulas

- **Event scope** — a bounded window filtered by `event_date` / `_TABLE_SUFFIX`; never unbounded.
- **Session key** — `(user_pseudo_id, ga_session_id)` where `ga_session_id` is taken from `event_params`. `ga_session_id` alone is **not** unique (it is a seconds timestamp) and must never be used alone.
- **Session definitions** — a session "reaches a step" in the **presence funnel** if it contains at least one event of that name; in the **ordered funnel** only if the event occurs after the previous step (window function over `event_timestamp`). Every metric below says which variant it uses.
- **Revenue fields** — `purchase_revenue_in_usd` and other `*_in_usd` fields (cross-currency-safe; see the [data dictionary callout](data_dictionary.md#currency-safety)).
- **Order** — a distinct `(user_pseudo_id, ecommerce.transaction_id)` pair on `purchase` events.

## Metric summary

| # | Metric | Level | Target sprint | Validation status |
|---|---|---|---|---|
| M01 | Event Count | Event | 01–02 | `PROPOSED` · `BLOCKED (NO BIGQUERY ACCESS)` |
| M02 | Observed Users | User | 02 | `PROPOSED` · `BLOCKED (NO BIGQUERY ACCESS)` |
| M03 | Sessions | Session | 02 | `PROPOSED` · `BLOCKED (NO BIGQUERY ACCESS)` |
| M04 | Product View Sessions | Session | 03 | `PROPOSED` · `BLOCKED (NO BIGQUERY ACCESS)` |
| M05 | Add-to-Cart Sessions | Session | 03 | `PROPOSED` · `BLOCKED (NO BIGQUERY ACCESS)` |
| M06 | Checkout Sessions | Session | 03 | `PROPOSED` · `BLOCKED (NO BIGQUERY ACCESS)` |
| M07 | Purchase Sessions | Session | 03 | `PROPOSED` · `BLOCKED (NO BIGQUERY ACCESS)` |
| M08 | Session Purchase Conversion Rate | Session | 03 | `PROPOSED` · `BLOCKED (NO BIGQUERY ACCESS)` |
| M09 | Funnel Step Conversion Rate | Session | 03 | `PROPOSED` · funnel monotonicity invariant `IMPLEMENTED (LOCAL)` |
| M10 | Drop-off Rate | Session | 03 | `PROPOSED` · `BLOCKED (NO BIGQUERY ACCESS)` |
| M11 | Revenue | Order | 04 | `PROPOSED` · `BLOCKED (NO BIGQUERY ACCESS)` |
| M12 | Average Order Value | Order | 04 | `PROPOSED` · `BLOCKED (NO BIGQUERY ACCESS)` |
| M13 | Order Count | Order | 04 | `PROPOSED` · `BLOCKED (NO BIGQUERY ACCESS)` |
| M14 | Revenue per Session | Session | 04 | `PROPOSED` · `BLOCKED (NO BIGQUERY ACCESS)` |
| M15 | Products per Order | Order | 04 | `PROPOSED` · `BLOCKED (NO BIGQUERY ACCESS)` |
| M16 | Repeat Purchase Rate | User | 06 | `PROPOSED` · `BLOCKED (NO BIGQUERY ACCESS)` — not implemented |
| M17 | Time to Purchase | Session / User | 06 | `PROPOSED` · `BLOCKED (NO BIGQUERY ACCESS)` — not implemented |
| M18 | New vs Returning Users | User | 06 | `PROPOSED` · `BLOCKED (NO BIGQUERY ACCESS)` — not implemented |

---

## M01 · Event Count

- **Business interpretation:** Raw volume of tracked activity. Baseline for coverage checks and for spotting logging regressions — not a business outcome by itself.
- **Formula:** `COUNT(*)` over events in scope.
- **Numerator / denominator:** none — a total, not a ratio.
- **Aggregation level:** event; roll-ups to day / session / user are derived.
- **Required data fields:** `event_date`, `event_name`, `event_timestamp` ([data dictionary §1](data_dictionary.md#1-top-level-fields)).
- **Limitations:** includes `debug_mode` events and non-user-facing events unless filtered; inflated by duplicate logging (client + server side). Counts events, not people or visits.
- **Validation status:** `PROPOSED` · `BLOCKED (NO BIGQUERY ACCESS)`.

## M02 · Observed Users

- **Business interpretation:** How many distinct pseudonymous users were observed in the window — the audience-size baseline for every per-user metric.
- **Formula:** `COUNT(DISTINCT user_pseudo_id)` over the scoped events.
- **Numerator / denominator:** none — distinct count.
- **Aggregation level:** user (per query window).
- **Required data fields:** `user_pseudo_id`, `event_date` ([§1](data_dictionary.md#1-top-level-fields)).
- **Limitations:** `user_pseudo_id` is per-device/browser, not per-human — cross-device duplication; cookie resets create new IDs. Distinct users **per day summed ≠ distinct users over a period** (see traps). GA UI "Active users" uses estimation (HLL++); BigQuery counts are exact but differ slightly from UI reports ([source](https://support.google.com/analytics/answer/9191807)).
- **Validation status:** `PROPOSED` · `BLOCKED (NO BIGQUERY ACCESS)`.

## M03 · Sessions

- **Business interpretation:** The unit of the funnel. "How many visit opportunities did we have?" — the denominator of most conversion metrics.
- **Formula:** number of distinct `(user_pseudo_id, ga_session_id)` pairs — in SQL, `COUNT(DISTINCT STRUCT(user_pseudo_id, ga_session_id))` (or an equivalent concatenation with a separator that cannot occur in the values).
- **Numerator / denominator:** none — distinct count of session keys.
- **Aggregation level:** session.
- **Required data fields:** `user_pseudo_id`, `event_params` → `ga_session_id` ([§2](data_dictionary.md#2-important-event_params-keys)).
- **Limitations:** events with a **missing/empty `ga_session_id` cannot be attributed to a session**; they are excluded from session metrics and their share must be published alongside (not hidden). Sessions spanning midnight belong to the day they started (`event_date` of their events may differ). Session counts in BigQuery differ slightly from GA UI counts due to HLL++ estimation in reports ([source](https://support.google.com/analytics/answer/9191807)).
- **Validation status:** `PROPOSED` · `BLOCKED (NO BIGQUERY ACCESS)`.

## M04 · Product View Sessions

- **Business interpretation:** Sessions that showed interest in at least one product — top of the purchase funnel.
- **Formula:** sessions in scope with ≥ 1 `view_item` event (presence funnel).
- **Numerator / denominator:** none — count of distinct session keys meeting the condition.
- **Aggregation level:** session.
- **Required data fields:** `event_name`, `user_pseudo_id`, `ga_session_id` ([§1](data_dictionary.md#1-top-level-fields), [§2](data_dictionary.md#2-important-event_params-keys)).
- **Limitations:** depends on the store emitting `view_item` correctly and consistently; product-list interactions (`view_item_list`) are a different event and are not counted here. Multiple `view_item` events in one session count once.
- **Validation status:** `PROPOSED` · `BLOCKED (NO BIGQUERY ACCESS)`.

## M05 · Add-to-Cart Sessions

- **Business interpretation:** Sessions where intent turned into a concrete action — the first commitment step.
- **Formula:** sessions in scope with ≥ 1 `add_to_cart` event (presence funnel).
- **Numerator / denominator:** none — distinct session keys meeting the condition.
- **Aggregation level:** session.
- **Required data fields:** `event_name`, `user_pseudo_id`, `ga_session_id`.
- **Limitations:** carts are not purchases; repeated adds count once per session. `remove_from_cart` exists but is not netted out in the presence definition (documented as a known simplification).
- **Validation status:** `PROPOSED` · `BLOCKED (NO BIGQUERY ACCESS)`.

## M06 · Checkout Sessions

- **Business interpretation:** Sessions that started checkout — the highest-intent step before money changes hands.
- **Formula:** sessions in scope with ≥ 1 `begin_checkout` event (presence funnel).
- **Numerator / denominator:** none — distinct session keys meeting the condition.
- **Aggregation level:** session.
- **Required data fields:** `event_name`, `user_pseudo_id`, `ga_session_id`.
- **Limitations:** `begin_checkout` may fire more than once per session (multiple attempts); presence definition counts the session once. Stores that skip the explicit checkout event break this step — to be confirmed against the live event catalog.
- **Validation status:** `PROPOSED` · `BLOCKED (NO BIGQUERY ACCESS)`.

## M07 · Purchase Sessions

- **Business interpretation:** Sessions that ended in at least one purchase — the funnel's terminal step.
- **Formula:** sessions in scope with ≥ 1 `purchase` event (presence funnel).
- **Numerator / denominator:** none — distinct session keys meeting the condition.
- **Aggregation level:** session.
- **Required data fields:** `event_name`, `user_pseudo_id`, `ga_session_id`, `ecommerce.transaction_id` (for duplicate control).
- **Limitations:** a session can contain a duplicated `purchase` event; the session itself still counts once, so M07 is robust to the duplication trap that affects M11/M13. Sessions containing only a `refund` are not purchases.
- **Validation status:** `PROPOSED` · `BLOCKED (NO BIGQUERY ACCESS)`.

## M08 · Session Purchase Conversion Rate

- **Business interpretation:** Of all visit opportunities, what share converted — the headline efficiency metric for acquisition and UX decisions.
- **Formula:** `Purchase Sessions ÷ Sessions`.
- **Numerator:** sessions containing ≥ 1 `purchase` (M07). **Denominator:** all sessions in scope (M03).
- **Aggregation level:** session (always reported with the same scope and window for numerator and denominator).
- **Required data fields:** `event_name`, `user_pseudo_id`, `ga_session_id`.
- **Limitations:** app/store sessions inflate the denominator relative to intent-driven traffic; must always be segmented (device, channel) before acting on it. Not comparable to GA UI "session key event rate" (different scopes, HLL++ estimation). Small windows produce unstable rates.
- **Validation status:** `PROPOSED` · `BLOCKED (NO BIGQUERY ACCESS)`.

## M09 · Funnel Step Conversion Rate

- **Business interpretation:** The single most decision-relevant family of metrics: *where* in the journey users are lost, step by step.
- **Formula (ordered variant):** for steps `A → B` (e.g. `view_item → add_to_cart`): `Ordered Sessions reaching B ÷ Ordered Sessions reaching A`, where "reaching" uses the first occurrence of each step and requires the step-B timestamp to be after the step-A timestamp.
- **Numerator:** sessions whose first `B` event occurs after their first `A` event. **Denominator:** sessions that reach step `A` at all.
- **Aggregation level:** session; reported per step pair and per segment (device, channel).
- **Required data fields:** `event_name`, `event_timestamp`, `user_pseudo_id`, `ga_session_id`.
- **Limitations:** event names alone do not encode intent — a low step rate defines *what to investigate*, never *why*. Equal timestamps need an explicit tie-breaking policy (documented in the SQL). The presence variant and ordered variant of the same funnel **give different numbers by construction** — the variant must be stated with every result.
- **Validation status:** `PROPOSED` · funnel monotonicity as a structural invariant is `IMPLEMENTED (LOCAL)` (synthetic fixtures); the business metric is `BLOCKED (NO BIGQUERY ACCESS)`.

## M10 · Drop-off Rate

- **Business interpretation:** The complement of the step rate, voiced as "how many sessions we lose here" — used to prioritize where a fix is worth testing first.
- **Formula:** `1 − Funnel Step Conversion Rate` for the same step pair (M09).
- **Numerator / denominator:** directly derived from M09 (no independent count).
- **Aggregation level:** session.
- **Required data fields:** same as M09.
- **Limitations:** inherits all M09 limitations. A high drop-off step is a *hypothesis input*, not proof of a defect — some step losses are legitimate (researching users, price checks).
- **Validation status:** `PROPOSED` · `BLOCKED (NO BIGQUERY ACCESS)`.

## M11 · Revenue

- **Business interpretation:** Money attributed to purchases observed in the window — the business outcome the funnel ultimately serves.
- **Formula:** `SUM(ecommerce.purchase_revenue_in_usd)` over **de-duplicated** purchase events (per user + `transaction_id`).
- **Numerator / denominator:** none — total.
- **Aggregation level:** order → day / session / user / product roll-ups.
- **Required data fields:** `ecommerce.purchase_revenue_in_usd`, `ecommerce.transaction_id`, `user_pseudo_id`, `event_timestamp` ([§1.2](data_dictionary.md#12-ecommerce-record-children)).
- **Limitations:** **gross of refunds** unless refund events are netted (Sprint 04+); duplicated purchase events (client + server logging) would double-count revenue if not de-duplicated on `transaction_id`; `purchase` events without a `transaction_id` cannot be de-duplicated and are excluded from revenue with their share reported. Local-currency `purchase_revenue` is never used (see [currency callout](data_dictionary.md#currency-safety)).
- **Validation status:** `PROPOSED` · `BLOCKED (NO BIGQUERY ACCESS)`.

## M12 · Average Order Value

- **Business interpretation:** Typical order size — the multiplier that converts conversion gains into revenue expectations.
- **Formula:** `Revenue ÷ Order Count`.
- **Numerator:** M11 (revenue over unique orders). **Denominator:** M13 (distinct orders) — **unique orders, never raw `purchase` events**.
- **Aggregation level:** order (aggregated over day / channel / segment).
- **Required data fields:** `ecommerce.purchase_revenue_in_usd`, `ecommerce.transaction_id`, `user_pseudo_id`.
- **Limitations:** mixing orders from different segments without grouping hides the real distribution (AOV can mask a bimodal mix); refunds not netted; undefined when order count is 0 (must render as "no data", never as 0).
- **Validation status:** `PROPOSED` · `BLOCKED (NO BIGQUERY ACCESS)`.

## M13 · Order Count

- **Business interpretation:** How many completed, de-duplicated purchases occurred — the honest denominator for AOV and per-order metrics.
- **Formula:** `COUNT(DISTINCT (user_pseudo_id, ecommerce.transaction_id))` on `purchase` events.
- **Numerator / denominator:** none — distinct count.
- **Aggregation level:** order.
- **Required data fields:** `ecommerce.transaction_id`, `user_pseudo_id`, `event_name`.
- **Limitations:** `NULL`/empty `transaction_id` purchases cannot be de-duplicated → excluded from the count and reported separately; two different users reusing one `transaction_id` count as two orders (key is scoped per user).
- **Validation status:** `PROPOSED` · `BLOCKED (NO BIGQUERY ACCESS)`.

## M14 · Revenue per Session

- **Business interpretation:** Traffic value normalized by visit opportunity — compares channels and periods with different traffic volumes.
- **Formula:** `Revenue ÷ Sessions`.
- **Numerator:** M11. **Denominator:** M03 — same window and scope.
- **Aggregation level:** session-based aggregate.
- **Required data fields:** M11 and M03 fields.
- **Limitations:** small windows are dominated by single large orders (unstable); inherits duplicate-revenue and session-attribution caveats.
- **Validation status:** `PROPOSED` · `BLOCKED (NO BIGQUERY ACCESS)`. Target: Sprint 04.

## M15 · Products per Order

- **Business interpretation:** Basket composition — a rising trend supports bundling/cross-sell hypotheses.
- **Formula (units variant):** `SUM(items.quantity) on purchase events ÷ Order Count`. (Alternative "unique items" variant: `ecommerce.unique_items`.)
- **Numerator:** total item units across de-duplicated purchase orders. **Denominator:** M13.
- **Aggregation level:** order.
- **Required data fields:** `items.quantity`, `items.item_id`, `ecommerce.unique_items`, order key fields.
- **Limitations:** `quantity` defaults to 1 when not sent, systematically understating true basket sizes if the store does not pass it; item arrays can be missing on some purchases; measured per order (de-duplicated), never per purchase event.
- **Validation status:** `PROPOSED` · `BLOCKED (NO BIGQUERY ACCESS)`. Target: Sprint 04.

## M16 · Repeat Purchase Rate

- **Business interpretation:** Share of buyers who came back — the retention signal behind lifetime-value questions.
- **Formula:** `Buyers with ≥ 2 distinct orders ÷ Buyers with ≥ 1 order` (same window).
- **Numerator:** distinct `user_pseudo_id` with ≥ 2 distinct `transaction_id`. **Denominator:** distinct `user_pseudo_id` with ≥ 1 purchase.
- **Aggregation level:** user.
- **Required data fields:** `user_pseudo_id`, `ecommerce.transaction_id`, `event_timestamp`; `user_first_touch_timestamp` for first-visit context.
- **Limitations:** **severely biased by the short sample window (3 months)** — users whose second purchase falls outside the window are counted as one-time buyers; device-level identity fragments purchases. Never compare this value across windows without holding the window length fixed.
- **Validation status:** `PROPOSED` · not implemented · `BLOCKED (NO BIGQUERY ACCESS)`. Target: Sprint 06.

## M17 · Time to Purchase

- **Business interpretation:** How long the journey takes — informs retargeting windows and expectation-setting for conversion curves.
- **Formula (session variant):** `purchase.event_timestamp − first event timestamp of the same session`. (User variant: `− user_first_touch_timestamp`.)
- **Numerator / denominator:** none — distribution metric (median, percentiles); never reported as a single mean alone.
- **Aggregation level:** session (session variant) / user (user variant); both reported.
- **Required data fields:** `event_timestamp`, `user_pseudo_id`, `ga_session_id`, `event_name`; + `user_first_touch_timestamp` for the user variant.
- **Limitations:** **survivorship bias** — only purchasers are included; users who never buy have no timestamp and are invisible to this metric. Microsecond units must be converted consistently. Same-window truncation biases the user variant upward.
- **Validation status:** `PROPOSED` · not implemented · `BLOCKED (NO BIGQUERY ACCESS)`. Target: Sprint 06.

## M18 · New vs Returning Users

- **Business interpretation:** Whether growth comes from acquisition or from existing users — the core acquisition/retention split.
- **Formula (window-relative):** user is **new** if `MIN(event_timestamp)` within the window equals `user_first_touch_timestamp` (first touch occurs inside the window); otherwise **returning**.
- **Numerator / denominator:** reported as counts and as shares of M02 (observed users) per class.
- **Aggregation level:** user.
- **Required data fields:** `user_pseudo_id`, `event_timestamp`, `user_first_touch_timestamp`.
- **Limitations:** `user_first_touch_timestamp` is device/browser-scoped, not human-scoped; the sample window starts 2020-11-01, so every user's "first touch" visible in the data may actually precede the window — the split is only reliable once the query looks back far enough.
- **Validation status:** `PROPOSED` · not implemented · `BLOCKED (NO BIGQUERY ACCESS)`. Target: Sprint 06.

---

## Metric traps

These are the specific ways these numbers go wrong. Every implementation must handle them; every published metric must disclose which apply.

| # | Trap | Consequence | Handling rule |
|---|---|---|---|
| T1 | **Events ≠ sessions.** Counting `purchase` events as "orders" or `view_item` events as "visitors" inflates everything. | Order counts and conversion rates off by the duplication factor. | Count at the documented grain (session, order, user) — never at event grain by accident. |
| T2 | **Distinct users per day summed ≠ distinct users over a period.** A user active on three days is one person, three daily rows. | Period totals double/triple-count users; daily series cannot be summed. | Distinct counts only within the exact reported window; period DAU charts use per-day counts and are never summed into a period total. |
| T3 | **`purchase` duplicated client + server side.** The same transaction can appear multiple times. | Revenue and order counts inflated. | De-duplicate on `(user_pseudo_id, transaction_id)` before any revenue math (M11/M12/M13). |
| T4 | **`purchase_revenue` is local currency, `purchase_revenue_in_usd` is USD.** Summing the local-currency field across a multi-currency window mixes units. | Revenue sum is meaningless (dollars + euros) whenever more than one currency is present. | Use `purchase_revenue_in_usd` / `price_in_usd` / `item_revenue_in_usd` everywhere; confirm the currency mix with `06_purchase_revenue_audit.sql` query 3. |
| T4b | **"`purchase_revenue` is NULL when the event currency ≠ property currency"** — a widely repeated claim that the documentation review for this project could **not** confirm (`[UNRESOLVED]`, `dataset_research.md` §10.2). | If believed and false, the team may stop measuring the NULL rate and miss a real completeness problem — or invent one that does not exist. | Treat as unproven. Measure it: `06_purchase_revenue_audit.sql` query 2 reports the NULL rate of each revenue field separately. Report any asymmetry as an **observed finding with the query as evidence**, never as documented behaviour. |
| T5 | **First-user acquisition ≠ session attribution.** `traffic_source` describes who acquired the user, not how this session arrived; `session_traffic_source_last_click` (if present) and `collected_traffic_source` describe session context. | Channel reports misattribute revenue to the acquisition channel of the user rather than the session. | Never mix the two scopes; label every channel chart with its scope ("session" or "first user"). |
| T6 | **AOV denominator must be unique orders, not purchase events.** Using purchase-event count lowers AOV wherever duplicates exist. | Wrong AOV, wrong scenario math in the Growth Opportunity Engine. | AOV = Revenue ÷ distinct orders (M12/M13), always. |
| T7 | **No ad-spend data exists in the dataset.** | **CAC and ROAS cannot be computed** from this data. | Say so; acquisition analysis describes behavior and value, never profitability. |
| T8 | **Missing `ga_session_id`.** Some events carry no session ID (and the export documents cases where the ID is not on `session_start`). | Session metrics silently shrink denominator/numerator differently. | Exclude the events **and publish their share** — never impute a session. |
| T9 | **Session ID collisions.** `ga_session_id` is a seconds timestamp; identical across users. | Grouping by `ga_session_id` alone merges unrelated sessions. | Always group by `(user_pseudo_id, ga_session_id)`. |
| T10 | **Obfuscated, partially adjusted data.** Placeholder values (`<Other>`, `NULL`, `''`) exist by design. | Segment splits can be distorted (e.g. a large "unknown" bucket). | Report coverage of key dimensions with every segment analysis; treat values as structure-illustrative. |
| T11 | **GA UI vs BigQuery counting differences.** Reports use estimation (HLL++) and different scopes. | "Our number disagrees with GA" is expected, not necessarily a bug. | Document the source of each number; never silently reconcile to the UI. |

## Re-verification plan (Sprint 02, first task)

1. Run the exploration queries and record actual counts for M01–M03 (structure checks).
2. Cross-check `COUNT(DISTINCT user_pseudo_id || ga_session_id)` against an independent aggregation over `session_start` events; record the gap.
3. Confirm the `currency` distribution and the `purchase_revenue` vs `purchase_revenue_in_usd` NULL pattern (T4).
4. Measure the duplicate-rate of purchase events before and after `transaction_id` de-duplication (T3).
5. Promote each metric to `IMPLEMENTED (LOCAL)` only when its SQL exists and passes a synthetic-data unit test; to `VERIFIED (LIVE)` only with a recorded cross-check.
