"""Pytest configuration and **synthetic** DataFrames for the GrowthScope quality tests.

Fixture policy (see also ``tests/fixtures/README.md``)
------------------------------------------------------
Every frame defined here is **SYNTHETIC**: hand-written numbers, built only to
exercise the code paths of ``growthscope.quality.checks``. They are *not* samples
of the GA4 sample dataset, they must never be used to illustrate a real finding,
and no number derived from them may appear in ``docs/data_quality_audit.md`` as a
result about the real data.

The GA4 sample export itself is not available in this environment (no BigQuery
credentials), which is precisely why the checks are designed to run on small,
already-fetched aggregates: that makes the whole validation library testable
without cloud access.

Columns use the real GA4 field names (``user_pseudo_id``, ``ga_session_id``,
``event_timestamp``, ``transaction_id``, ``purchase_revenue``,
``purchase_revenue_in_usd``) so the fixtures stay recognisable next to the SQL
queries in ``sql/exploration/``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

# Make ``src/`` importable when the project is not installed as a package yet.
# ``pyproject.toml`` (owned by another subagent) is expected to add the same
# path; keeping this bootstrap makes the test suite runnable on its own.
_SRC = Path(__file__).resolve().parents[1] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# ---------------------------------------------------------------------------
# Synthetic fixtures — session-level aggregates
# ---------------------------------------------------------------------------


@pytest.fixture()
def syn_session_df() -> pd.DataFrame:
    """SYNTHETIC 6-row session-level aggregate with known defects.

    Deliberate content (used by several tests, keep in sync with the tests):

    * 1 of 6 rows has no ``user_pseudo_id`` (empty string) -> 16.67% missing id.
    * ``(u1, 1001)`` appears twice -> exactly 1 duplicated composite key, 2 rows.
    * ``ga_session_id = 1001`` is shared by ``u1`` and ``u3`` (plus one excluded
      row whose user id is missing) -> exactly 1 cross-user reuse.
    * single currency (USD) -> the currency check passes.

    NOTE: ``u1/u2/u3`` (text ids) and session ids 1001..1004 are made up.
    """
    return pd.DataFrame(
        {
            "user_pseudo_id": ["u1", "u1", "u2", "u2", "", "u3"],
            "ga_session_id": [1001, 1001, 1002, 1003, 1004, 1001],
            "session_date": pd.to_datetime(
                ["2021-01-01", "2021-01-01", "2021-01-02", "2021-01-03", "2021-01-04", "2021-01-05"]
            ),
            "sessions": [1, 1, 1, 1, 1, 1],
            "conversion_rate": [0.0, 0.0, 0.5, 0.25, 0.0, 1.0],
            "currency": ["USD"] * 6,
        }
    )


@pytest.fixture()
def syn_clean_session_df() -> pd.DataFrame:
    """SYNTHETIC 4-row session aggregate with no key defects.

    Unique ``(user_pseudo_id, ga_session_id)`` pairs, unique session ids, no
    missing ids, one currency: every check in the library should pass on it.
    """
    return pd.DataFrame(
        {
            "user_pseudo_id": ["u1", "u1", "u2", "u2"],
            "ga_session_id": [1001, 1002, 2001, 2002],
            "session_date": pd.to_datetime(["2021-01-01", "2021-01-02", "2021-01-03", "2021-01-04"]),
            "sessions": [1, 1, 1, 1],
            "conversion_rate": [0.0, 0.5, 0.0, 1.0],
            "currency": ["USD", "USD", "USD", "USD"],
        }
    )


@pytest.fixture()
def syn_missing_key_df() -> pd.DataFrame:
    """SYNTHETIC 3-row aggregate in which *every* key component is missing.

    Used to prove the "no complete key" branches behave and do not crash.
    """
    return pd.DataFrame(
        {
            "user_pseudo_id": ["", None, "   "],
            "ga_session_id": [1001, 1002, 1003],
            "currency": ["USD", "USD", "USD"],
        }
    )


# ---------------------------------------------------------------------------
# Synthetic fixtures — purchases
# ---------------------------------------------------------------------------


@pytest.fixture()
def syn_purchase_df() -> pd.DataFrame:
    """SYNTHETIC 5-row purchase aggregate with deliberate duplicate + missing ids.

    * ``T-1001`` appears twice with ``purchase_revenue = 100.0`` on both rows ->
      summing revenue naively double-counts 100.0 (the exact bug the check exists
      for).
    * one NULL and one empty-string ``transaction_id`` -> not a duplicate group.
    * ``purchase_revenue`` is NULL on the two rows without an id, while
      ``purchase_revenue_in_usd`` is populated -> mirrors the documented GA4
      situation where the store currency differs from the property currency.
    """
    return pd.DataFrame(
        {
            "transaction_id": ["T-1001", "T-1001", None, "", "T-1002"],
            "purchase_revenue": [100.0, 100.0, None, None, 50.0],
            "purchase_revenue_in_usd": [100.0, 100.0, 80.0, 80.0, 50.0],
            "currency": ["USD"] * 5,
        }
    )


@pytest.fixture()
def syn_purchase_clean_df() -> pd.DataFrame:
    """SYNTHETIC 3-row purchase aggregate with unique, present transaction ids."""
    return pd.DataFrame(
        {
            "transaction_id": ["T-2001", "T-2002", "T-2003"],
            "purchase_revenue": [10.0, 20.0, 30.0],
            "purchase_revenue_in_usd": [10.0, 20.0, 30.0],
            "currency": ["USD"] * 3,
        }
    )


# ---------------------------------------------------------------------------
# Synthetic fixtures — daily series and funnels
# ---------------------------------------------------------------------------


@pytest.fixture()
def syn_daily_df() -> pd.DataFrame:
    """SYNTHETIC 4-row daily series with ONE deliberate gap.

    Days present: 2021-01-01, 01-02, 01-04, 01-05. The window
    ``2021-01-01 .. 2021-01-05`` therefore misses exactly ``2021-01-03``.
    """
    return pd.DataFrame(
        {
            "event_date": pd.to_datetime(["2021-01-01", "2021-01-02", "2021-01-04", "2021-01-05"]),
            "sessions": [10, 12, 9, 11],
        }
    )


FUNNEL_STEP_COLUMNS = [
    "step_1_view_item",
    "step_2_add_to_cart",
    "step_3_begin_checkout",
    "step_4_add_payment_info",
    "step_5_purchase",
]


@pytest.fixture()
def syn_funnel_monotonic_df() -> pd.DataFrame:
    """SYNTHETIC single-row session funnel whose counts never grow."""
    return pd.DataFrame([dict(zip(FUNNEL_STEP_COLUMNS, [1000, 600, 250, 120, 45]))])


@pytest.fixture()
def syn_funnel_non_monotonic_df() -> pd.DataFrame:
    """SYNTHETIC single-row funnel where step 3 (650) exceeds step 2 (600).

    Impossible for a correctly built nested session funnel, so it must be
    reported as a violation.
    """
    return pd.DataFrame([dict(zip(FUNNEL_STEP_COLUMNS, [1000, 600, 650, 120, 45]))])


@pytest.fixture()
def syn_funnel_mixed_df() -> pd.DataFrame:
    """SYNTHETIC 2-row funnel: segment A is monotonic, segment B is broken.

    Used to prove violations are counted per row, not just detected globally.
    """
    return pd.DataFrame(
        [
            dict(zip(FUNNEL_STEP_COLUMNS, [1000, 600, 250, 120, 45])),
            dict(zip(FUNNEL_STEP_COLUMNS, [500, 300, 320, 100, 20])),
        ],
        index=["segment_a", "segment_b"],
    )


@pytest.fixture()
def syn_funnel_with_null_df() -> pd.DataFrame:
    """SYNTHETIC funnel with a NULL step count (an unverifiable comparison).

    The step is ``NaN`` rather than ``None`` so the column keeps a numeric dtype,
    which is what a BigQuery aggregate returns for a missing COUNT.
    """
    values = dict(zip(FUNNEL_STEP_COLUMNS, [1000, 600, 250, 120, 45]))
    values["step_3_begin_checkout"] = float("nan")
    return pd.DataFrame([values])


# ---------------------------------------------------------------------------
# Synthetic fixtures — currency, timestamps, shares
# ---------------------------------------------------------------------------


@pytest.fixture()
def syn_multicurrency_df() -> pd.DataFrame:
    """SYNTHETIC revenue rows mixing currencies (plus a placeholder and NULL)."""
    return pd.DataFrame(
        {
            "currency": ["USD", "usd ", "EUR", None, "(not set)"],
            "purchase_revenue": [100.0, 50.0, 9000.0, None, 10.0],
        }
    )


@pytest.fixture()
def syn_timestamp_df() -> pd.DataFrame:
    """SYNTHETIC event timestamps in GA4 **microseconds**, two of them implausible.

    * 1610000000000000 -> 2021-01-07T06:13:20Z (inside the 2021-01 window)
    * 1000             -> the classic "seconds value read as microseconds" trap
    * 99999999999999999 -> far in the future (a millisecond/second mix-up)
    * NULL             -> an expression produced a NULL timestamp
    """
    return pd.DataFrame(
        {
            "event_timestamp": pd.array(
                [1610000000000000, 1610000000000001, 1000, 99999999999999999, None],
                dtype="Int64",
            ),
        }
    )


@pytest.fixture()
def syn_timestamp_clean_df() -> pd.DataFrame:
    """SYNTHETIC timestamps that all sit inside the 2021-01 window (micros)."""
    return pd.DataFrame(
        {"event_timestamp": pd.array([1610000000000000, 1609459200000000], dtype="Int64")}
    )


@pytest.fixture()
def syn_share_df() -> pd.DataFrame:
    """SYNTHETIC rate column with two impossible values (1.5 and -0.1) and a NULL."""
    return pd.DataFrame({"conversion_rate": [0.0, 0.42, 1.0, 1.5, -0.1, None]})


@pytest.fixture()
def syn_text_numbers_df() -> pd.DataFrame:
    """SYNTHETIC frame holding numbers as text (the wrong-dtype error path)."""
    return pd.DataFrame(
        {
            "user_pseudo_id": ["u1", "u2"],
            "event_timestamp": ["1610000000000000", "1610000000000001"],
            "purchase_revenue": ["100.0", "50.0"],
            "conversion_rate": ["0.5", "1.5"],
        }
    )


# ---------------------------------------------------------------------------
# Optional real aggregates (only if a human added them on purpose)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def real_aggregate_fixtures() -> dict[str, pd.DataFrame]:
    """Load every CSV in ``tests/fixtures/`` (session scope), or ``{}`` if none.

    The directory is expected to contain **small, aggregated, non-PII** exports
    only - never raw user-level GA4 rows. See ``tests/fixtures/README.md``. Tests
    consuming this fixture skip themselves when it is empty, so the suite passes
    on a clean checkout.
    """
    directory = Path(__file__).resolve().parent / "fixtures"
    frames: dict[str, pd.DataFrame] = {}
    if directory.is_dir():
        for csv_path in sorted(directory.glob("*.csv")):
            frames[csv_path.stem] = pd.read_csv(csv_path)
    return frames
