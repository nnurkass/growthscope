"""Deterministic data-quality checks for GA4-derived aggregates.

Scope
-----
Every function here takes a **pandas DataFrame that was already produced by a SQL
exploration query** over ``bigquery-public-data.ga4_obfuscated_sample_ecommerce``
(session-level aggregates, daily series, funnels, purchase rows, ...) and returns
a :class:`~growthscope.quality.models.CheckResult`. Nothing in this module reads
the raw dataset, touches the network or writes anything.

Why validate aggregates instead of raw events?
    1. The raw export is large (millions of nested rows); NULL rates and duplicate
       keys are far cheaper to compute in BigQuery than to transfer.
    2. The bugs that actually break GrowthScope's metrics are *aggregation* bugs
       (fan-out joins, a broken ``GROUP BY`` grain, a mis-ordered funnel step),
       and those are only visible in the aggregate.
    3. Checks that run on a DataFrame can be unit-tested with synthetic fixtures
       and are therefore trustworthy even when no cloud access is available.

GA4 semantics that every check has to respect (and that its docstring explains):
    * ``user_pseudo_id`` is a pseudonymous id derived from a cookie/device. It is
      legitimately **missing** for users who declined consent or block cookies -
      a missing id is an analytical limitation, not data corruption.
    * ``ga_session_id`` (the ``ga_session_id`` event parameter) is a
      timestamp-derived integer that is unique **per user**, not globally.
      ``(user_pseudo_id, ga_session_id)`` is the real session key.
    * ``event_timestamp`` is **microseconds** since the Unix epoch, not seconds
      and not milliseconds.
    * ``purchase_revenue`` is the revenue in the *event* currency (the currency
      stored on the purchase event), so it can be NULL/incomparable when a store
      currency differs from the property currency; ``purchase_revenue_in_usd`` is
      the standardised counterpart.
    * A single purchase can produce more than one ``purchase`` event row (retry,
      session continuation, "resume" flows), so revenue must be de-duplicated by
      ``transaction_id`` before summing.
    * Repeated *events* within one session are normal; repeated *rows* in a
      session-level aggregate are a bug.

Error contract
--------------
* ``TypeError`` - the input is not a DataFrame, a column name is not a string, a
  sequence argument was passed as a bare string, a column has a dtype that
  cannot answer the question (e.g. a text column for a timestamp),
* ``ValueError`` - a column is missing, or a parameter combination is invalid
  (e.g. ``min_ts > max_ts``, an empty ``step_columns`` list).

Empty frames are handled gracefully: each check documents what it returns for an
empty input instead of raising.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from .models import CheckResult, Severity

__all__ = [
    "check_currency_consistency",
    "check_date_coverage",
    "check_duplicate_composite_key",
    "check_funnel_monotonicity",
    "check_no_null_identifiers",
    "check_purchase_transaction_duplicates",
    "check_revenue_null_rate",
    "check_session_id_reuse",
    "check_share_bounds",
    "check_timestamp_validity",
    "micros_to_datetime",
]

# GA4 uses a handful of literal placeholder strings instead of NULLs.
GA4_PLACEHOLDERS = frozenset({"(not set)", "(not provided)", "<other>", "(none)", "null", "unknown"})


# ---------------------------------------------------------------------------
# internal helpers (kept private: they are implementation detail, not API)
# ---------------------------------------------------------------------------


def _require_frame(df: Any, func: str) -> pd.DataFrame:
    """Reject anything that is not a pandas DataFrame (fail fast, clear message)."""
    if not isinstance(df, pd.DataFrame):
        raise TypeError(
            f"{func}: expected a pandas DataFrame, got {type(df).__name__}. "
            "Pass the aggregate returned by the SQL exploration query."
        )
    return df


def _require_column_name(name: Any, func: str, param: str = "column") -> str:
    """Reject non-string column names (they would silently mis-index a frame)."""
    if not isinstance(name, str):
        raise TypeError(f"{func}: {param} must be a string, got {type(name).__name__}")
    if not name:
        raise ValueError(f"{func}: {param} must not be an empty string")
    return name


def _require_columns(df: pd.DataFrame, columns: Iterable[str], func: str) -> None:
    """Raise ``ValueError`` listing every column that is missing from the frame."""
    missing = [str(c) for c in columns if c not in df.columns]
    if missing:
        raise ValueError(
            f"{func}: column(s) {missing} not found in the DataFrame. "
            f"Available columns: {list(df.columns)}"
        )


def _require_column_list(columns: Any, func: str, param: str, min_len: int = 1) -> list[str]:
    """Validate a sequence-of-column-names argument and return it as a list."""
    if isinstance(columns, str):
        raise TypeError(
            f"{func}: {param} must be a sequence of column names, e.g. "
            f'["user_pseudo_id", "ga_session_id"], not a bare string'
        )
    if isinstance(columns, (set, frozenset)):
        raise TypeError(f"{func}: {param} must be an ordered sequence (list/tuple), not a set")
    if not isinstance(columns, Sequence):
        raise TypeError(
            f"{func}: {param} must be a sequence of column names, got {type(columns).__name__}"
        )
    normalized = [_require_column_name(c, func, f"{param}[{i}]") for i, c in enumerate(columns)]
    if len(normalized) < min_len:
        raise ValueError(f"{func}: {param} must contain at least {min_len} column name(s)")
    return normalized


def _require_rate(value: Any, func: str, param: str) -> float:
    """Validate a share/rate parameter (0.0 <= value <= 1.0)."""
    if isinstance(value, bool) or not isinstance(value, (int, float, np.integer, np.floating)):
        raise TypeError(f"{func}: {param} must be a number between 0.0 and 1.0, got {type(value).__name__}")
    number = float(value)
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"{func}: {param} must be between 0.0 and 1.0, got {value!r}")
    return number


def _missing_mask(series: pd.Series) -> pd.Series:
    """Boolean mask of "no usable identifier here".

    Covers NULL/NaN/NaT *and* empty/whitespace-only strings. GA4 exports and SQL
    aggregates both produce ``''`` where an analyst expects NULL, and an empty
    string behaves like a missing key in every join and every group-by.
    """
    mask = series.isna()
    if (
        pd.api.types.is_object_dtype(series)
        or isinstance(series.dtype, pd.StringDtype)
        or isinstance(series.dtype, pd.CategoricalDtype)
    ):
        text = series.astype("string").str.strip()
        mask = mask | text.eq("").fillna(False) | text.isna()
    return pd.Series(mask, index=series.index).astype(bool)


def _is_numeric_like(series: pd.Series) -> bool:
    """Numeric dtype, excluding booleans (a bool column is never a measurement)."""
    return bool(pd.api.types.is_numeric_dtype(series)) and not bool(pd.api.types.is_bool_dtype(series))


def _as_float_series(series: pd.Series, func: str, what: str) -> pd.Series:
    """Return the series as float64 (NaN for missing), or raise ``TypeError``."""
    if not _is_numeric_like(series) and not pd.api.types.is_datetime64_any_dtype(series):
        raise TypeError(
            f"{func}: {what} must have a numeric dtype, got '{series.dtype}'. "
            "Cast the column (e.g. with pd.to_numeric) before validating it."
        )
    try:
        values = series.to_numpy(dtype="float64", na_value=np.nan)
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
        raise TypeError(f"{func}: {what} could not be interpreted as numbers: {exc}") from exc
    return pd.Series(values, index=series.index, name=series.name)


def _to_timestamp(value: Any, func: str, param: str) -> pd.Timestamp:
    """Parse a date/datetime parameter into a tz-naive UTC-normalised Timestamp."""
    if value is None:
        raise ValueError(f"{func}: {param} must be a date, not None")
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{func}: {param}={value!r} could not be parsed as a date ({exc})") from exc
    if pd.isna(timestamp):
        raise ValueError(f"{func}: {param}={value!r} could not be parsed as a date")
    if timestamp.tz is not None:
        timestamp = timestamp.tz_convert("UTC").tz_localize(None)
    return timestamp.normalize()


def _to_micros(value: Any, func: str, param: str) -> int:
    """Normalise a timestamp bound into GA4 microseconds since the Unix epoch.

    Accepts an integer (already microseconds, the native GA4 unit) or any
    date/datetime/ISO string, which is converted with the same unit used by
    ``event_timestamp``.
    """
    if isinstance(value, bool):
        raise TypeError(f"{func}: {param} must be an int (microseconds) or a date, got bool")
    if isinstance(value, (pd.Timestamp, datetime, date)):
        timestamp = pd.Timestamp(value)
        if timestamp.tz is not None:
            timestamp = timestamp.tz_convert("UTC").tz_localize(None)
        return int(timestamp.value // 1000)  # Timestamp.value is nanoseconds
    if isinstance(value, str):
        return _to_micros(_to_timestamp(value, func, param), func, param)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        number = float(value)
        if not np.isfinite(number):
            raise ValueError(f"{func}: {param} must be a finite value, got {value!r}")
        return int(number)
    raise TypeError(
        f"{func}: {param} must be an int (microseconds since epoch) or a date/datetime, "
        f"got {type(value).__name__}"
    )


def _micros_series(series: pd.Series, func: str, what: str) -> pd.Series:
    """Return GA4 microsecond timestamps as float64 (NaN preserved).

    ``datetime64`` input (what ``TIMESTAMP_MICROS(...)`` returns) is converted
    back to microseconds, assuming UTC for timezone-naive values.
    """
    if pd.api.types.is_datetime64_any_dtype(series):
        present = series.notna()
        # pandas >= 3 keeps whatever resolution the column was parsed with (often
        # microseconds), so the raw int64 payload is NOT nanoseconds. `as_unit("ns")`
        # normalises the resolution first; NaT maps to the int64 sentinel and is
        # removed by the ``where`` below.
        nanos = pd.DatetimeIndex(series).as_unit("ns").asi8
        return pd.Series(nanos // 1000, index=series.index, dtype="float64").where(present)
    return _as_float_series(series, func, what)


def _iso_from_micros(value: float | None) -> str | None:
    """Render a microsecond timestamp as an ISO-8601 UTC string (for evidence)."""
    if value is None or not np.isfinite(value):
        return None
    return pd.Timestamp(int(value), unit="us", tz="UTC").isoformat()


def _sample(values: Sequence[Any], limit: int = 5) -> list[Any]:
    """Take at most ``limit`` items and stringify them for JSON-safe evidence."""
    return [str(v) for v in list(values)[:limit]]


def _empty_result(
    name: str,
    message: str,
    *,
    severity: Severity = Severity.INFORMATIONAL,
    passed: bool = True,
    evidence: dict[str, Any] | None = None,
) -> CheckResult:
    """Uniform result for an empty frame (no rows => nothing to measure)."""
    return CheckResult(
        name=name,
        passed=passed,
        severity=severity,
        metric_value=0 if passed else None,
        threshold=None,
        message=message,
        evidence=evidence or {},
    )


# ---------------------------------------------------------------------------
# public checks
# ---------------------------------------------------------------------------


def check_no_null_identifiers(
    df: pd.DataFrame,
    id_column: str = "user_pseudo_id",
    max_missing_rate: float = 0.0,
) -> CheckResult:
    """Measure the share of rows with no usable pseudonymous user id.

    GA4 semantics
    -------------
    ``user_pseudo_id`` is derived from a client-side identifier (cookie / device
    / app instance). It is **legitimately absent** when the user declined
    consent, blocks cookies, or arrives through a context where the identifier
    cannot be written. A NULL here is therefore an *analytical limitation*, not
    data corruption: the sessions still exist and still count for session-level
    metrics, but they cannot be attributed to a user, so they must be excluded
    from user-level funnel and retention maths.

    Reporting the rate (rather than just "some rows are NULL") lets downstream
    code shrink its denominators transparently, e.g.
    ``sessions_attributable = sessions_all * (1 - missing_rate)``.

    Parameters
    ----------
    df:
        Any row-level or session-level aggregate containing ``id_column``.
    id_column:
        Identifier column; NULL, empty and whitespace-only values all count as
        missing.
    max_missing_rate:
        Tolerance in ``[0, 1]``. Default ``0.0`` means "any missing id counts as
        a failure of the tolerance", which is the strict QA default.

    Returns
    -------
    CheckResult
        ``passed`` compares the observed rate with ``max_missing_rate``.
        ``severity`` is High when the rate is above tolerance (something must be
        excluded/documented downstream) and Informational otherwise. An empty
        frame returns a passing, Informational result with a 0.0 rate -
        "no rows" is a coverage problem for a different check, not this one.
    """
    func = "check_no_null_identifiers"
    _require_frame(df, func)
    column = _require_column_name(id_column, func, "id_column")
    _require_columns(df, [column], func)
    tolerance = _require_rate(max_missing_rate, func, "max_missing_rate")

    rows = int(df.shape[0])
    if rows == 0:
        return _empty_result(
            "no_null_identifiers",
            f"Empty frame: no rows to evaluate for {column!r}.",
            evidence={"column": column, "rows": 0, "missing_rows": 0, "missing_rate": 0.0},
        )

    missing_rows = int(_missing_mask(df[column]).sum())
    rate = missing_rows / rows
    passed = rate <= tolerance
    severity = Severity.INFORMATIONAL if passed else Severity.HIGH

    if missing_rows == 0:
        message = (
            f"All {rows} rows carry a {column!r} value; user-level funnel maths can use every row."
        )
    else:
        message = (
            f"{missing_rows} of {rows} rows ({rate:.2%}) have no {column!r}. "
            "In GA4 this is EXPECTED behaviour (consent mode, cookie restrictions, "
            "pseudonymous identifiers) and NOT data corruption: those sessions are still "
            "real and still count for session-level metrics, but they cannot be attributed "
            "to a user, so user-level funnel and retention denominators must exclude them "
            f"and the excluded share must be reported. Tolerance: {tolerance:.2%}."
        )

    return CheckResult(
        name="no_null_identifiers",
        passed=passed,
        severity=severity,
        metric_value=round(rate, 6),
        threshold=tolerance,
        message=message,
        evidence={
            "column": column,
            "rows": rows,
            "missing_rows": missing_rows,
            "missing_rate": round(rate, 6),
            "max_missing_rate": tolerance,
            "interpretation": "expected GA4 pseudonymous-id behaviour, not corruption",
        },
    )


def check_duplicate_composite_key(df: pd.DataFrame, key_columns: Sequence[str]) -> CheckResult:
    """Detect duplicated rows for a key that is supposed to be unique.

    GA4 semantics
    -------------
    In the raw export, one session contains many event rows, so
    ``(user_pseudo_id, ga_session_id)`` legitimately repeats **once per event**.
    In a *session-level aggregate* the same pair must appear exactly once. A
    duplicate therefore proves the aggregation lost its grain - the usual causes
    are a fan-out join (one-to-many joined back onto the session grain), a
    ``GROUP BY`` that forgot a key column, or a UNION of an overlapping export.
    Every downstream count that sums rows then over-counts sessions, which
    silently inflates funnel entries at the top of the funnel.

    Rows with a NULL/empty component of the key are excluded from duplicate
    detection and counted separately: an incomplete key cannot form a reliable
    group (and joins on ``''`` would combine unrelated sessions).

    Parameters
    ----------
    df:
        Session-level (or any grain-level) aggregate.
    key_columns:
        The columns that should form the unique key, e.g.
        ``["user_pseudo_id", "ga_session_id"]``. Must be a list/tuple of strings.

    Returns
    -------
    CheckResult
        ``passed`` is ``True`` only when no duplicated key group exists.
        Severity is High when duplicates are found (the grain is broken).
        An empty frame passes with a "nothing to check" message, and a frame
        with no complete key at all also passes while reporting how many rows
        were excluded - the missing-key problem is covered by
        :func:`check_no_null_identifiers`.
    """
    func = "check_duplicate_composite_key"
    _require_frame(df, func)
    keys = _require_column_list(key_columns, func, "key_columns", min_len=1)
    _require_columns(df, keys, func)

    rows = int(df.shape[0])
    if rows == 0:
        return _empty_result(
            "duplicate_composite_key",
            f"Empty frame: no rows to check for duplicate {' + '.join(keys)} keys.",
            evidence={"key_columns": keys, "rows": 0, "duplicate_groups": 0, "duplicate_rows": 0},
        )

    null_key_mask = pd.Series(False, index=df.index)
    for column in keys:
        null_key_mask = null_key_mask | _missing_mask(df[column])
    usable = df.loc[~null_key_mask]
    excluded_rows = int(null_key_mask.sum())

    if usable.shape[0] == 0:
        return CheckResult(
            name="duplicate_composite_key",
            passed=True,
            severity=Severity.MEDIUM,
            metric_value=0,
            threshold=0,
            message=(
                f"No row has a complete {' + '.join(keys)} key, so no duplicate key could be "
                "detected. This is a key-coverage problem, not a duplicate problem - see "
                "check_no_null_identifiers for the id-level finding."
            ),
            evidence={
                "key_columns": keys,
                "rows": rows,
                "rows_excluded_incomplete_key": excluded_rows,
                "duplicate_groups": 0,
                "duplicate_rows": 0,
            },
        )

    sizes = usable.groupby(keys, dropna=False, observed=True).size()
    duplicated = sizes[sizes > 1]
    duplicate_groups = int(duplicated.shape[0])
    duplicate_rows = int(duplicated.sum())
    passed = duplicate_groups == 0
    severity = Severity.INFORMATIONAL if passed else Severity.HIGH

    if passed:
        message = (
            f"All {usable.shape[0]} rows with a complete {' + '.join(keys)} key are unique: "
            "the aggregate kept the intended grain, so counting rows equals counting sessions."
        )
    else:
        message = (
            f"{duplicate_rows} rows share {duplicate_groups} duplicated "
            f"({' + '.join(keys)}) key(s). Repeated *events* are legitimate in GA4 (many events "
            "belong to one session), but a duplicated key in a session-level aggregate means the "
            "grain was broken - usually a fan-out join, a GROUP BY missing a key column, or "
            "overlapping export shards. Counting rows downstream would over-count sessions."
        )

    return CheckResult(
        name="duplicate_composite_key",
        passed=passed,
        severity=severity,
        metric_value=duplicate_rows,
        threshold=0,
        message=message,
        evidence={
            "key_columns": keys,
            "rows": rows,
            "rows_with_complete_key": int(usable.shape[0]),
            "rows_excluded_incomplete_key": excluded_rows,
            "duplicate_groups": duplicate_groups,
            "duplicate_rows": duplicate_rows,
            "sample_duplicate_keys": [
                " | ".join(str(part) for part in (index if isinstance(index, tuple) else (index,)))
                for index in list(duplicated.index)[:5]
            ],
        },
    )


def check_purchase_transaction_duplicates(
    df: pd.DataFrame,
    transaction_id_column: str = "transaction_id",
) -> CheckResult:
    """Flag the same ``transaction_id`` appearing in more than one purchase row.

    GA4 semantics
    -------------
    ``transaction_id`` is not set by GA4 itself; the site sends it on the
    ``purchase`` event. The same order can therefore be reported more than once -
    page reloads, retries after a network error, ``purchase`` re-fired in a later
    session, or a "resume payment" flow. Each of those rows also repeats
    ``purchase_revenue``, so summing revenue without de-duplicating by
    ``transaction_id`` double-counts real money. This check makes that risk
    explicit before any revenue metric is built on the aggregate.

    NULL/empty transaction ids are handled separately and are **not** treated as
    a duplicate group ("no id" is not a shared id). They are counted, because
    those rows cannot be de-duplicated at all and are a blind spot rather than a
    defect. Note that ``'(not set)'`` is a GA4 placeholder string, not NULL; it
    is treated as a missing id here since many rows can share it without sharing
    an order.

    Parameters
    ----------
    df:
        Purchase-level aggregate (one row per purchase event, ideally).
    transaction_id_column:
        Name of the transaction id column.

    Returns
    -------
    CheckResult
        ``passed`` is ``True`` when no non-missing id repeats. Severity is High
        when a repeat is found (revenue double-counting risk). An empty frame
        passes and reports a zero duplicate count.
    """
    func = "check_purchase_transaction_duplicates"
    _require_frame(df, func)
    column = _require_column_name(transaction_id_column, func, "transaction_id_column")
    _require_columns(df, [column], func)

    rows = int(df.shape[0])
    if rows == 0:
        return _empty_result(
            "purchase_transaction_duplicates",
            f"Empty frame: no purchase rows to check for duplicate {column!r}.",
            evidence={"column": column, "rows": 0, "duplicate_transaction_ids": 0, "duplicate_rows": 0},
        )

    series = df[column]
    missing_mask = _missing_mask(series)
    if pd.api.types.is_object_dtype(series) or isinstance(
        series.dtype, (pd.StringDtype, pd.CategoricalDtype)
    ):
        placeholder_mask = series.astype("string").str.strip().str.lower().isin(GA4_PLACEHOLDERS)
        missing_mask = missing_mask | placeholder_mask.fillna(False)
    missing_rows = int(missing_mask.sum())

    usable = series.loc[~missing_mask].astype("string").str.strip()
    counts = usable.value_counts()
    duplicated = counts[counts > 1]
    duplicate_ids = int(duplicated.shape[0])
    duplicate_rows = int(duplicated.sum())
    passed = duplicate_ids == 0
    severity = Severity.INFORMATIONAL if passed else Severity.HIGH

    if rows == missing_rows:
        message = (
            f"All {rows} purchase rows have a NULL/empty {column!r}: nothing can be "
            "de-duplicated, so any revenue total built on these rows carries double-counting "
            "risk that cannot be detected here."
        )
        severity = Severity.MEDIUM
    elif passed:
        message = (
            f"Each of the {int(usable.shape[0])} purchase rows carries a distinct {column!r}: "
            "summing revenue over these rows will not double-count a transaction. "
            f"{missing_rows} row(s) have no usable id and cannot be de-duplicated."
        )
    else:
        message = (
            f"{duplicate_ids} {column!r} value(s) appear in more than one purchase row "
            f"({duplicate_rows} rows in total, {missing_rows} further row(s) have no usable id). "
            "GA4 can emit the purchase event more than once for one order (reload, retry, "
            "resumed session) and repeats purchase_revenue on every row, so revenue must be "
            "de-duplicated by transaction_id before summing - otherwise the order is counted "
            "twice."
        )

    return CheckResult(
        name="purchase_transaction_duplicates",
        passed=passed,
        severity=severity,
        metric_value=duplicate_ids,
        threshold=0,
        message=message,
        evidence={
            "column": column,
            "rows": rows,
            "rows_with_transaction_id": int(usable.shape[0]),
            "rows_missing_transaction_id": missing_rows,
            "duplicate_transaction_ids": duplicate_ids,
            "duplicate_rows": duplicate_rows,
            "sample_duplicate_ids": _sample(list(duplicated.index)),
        },
    )


def check_funnel_monotonicity(df: pd.DataFrame, step_columns: Sequence[str]) -> CheckResult:
    """Verify that an ordered session funnel never grows from one step to the next.

    GA4 semantics
    -------------
    A properly built funnel counts sessions (or users) that performed step *k*,
    and those sets are nested: every session that reached step 3 also reached
    step 2. The counts are therefore non-increasing by construction. If step 3
    counts *more* sessions than step 2, the funnel was not built as a nesting: a
    ``LEFT JOIN`` without a null guard, a ``UNION`` of overlapping windows, a step
    ordered by the wrong timestamp, or a step filter that is not a superset of the
    next step. Such a funnel produces conversion rates above 100% and would be
    immediately visible to a judge or an interviewer.

    Evaluated row-wise, so the same function validates a single aggregate row
    (a whole-property funnel) or one row per segment (funnel per channel).

    Parameters
    ----------
    df:
        Aggregate whose columns are the ordered funnel step counts.
    step_columns:
        Step count columns **in funnel order** (step 1 first). At least two are
        required; they must be numeric.

    Returns
    -------
    CheckResult
        ``passed`` is ``True`` when no step is larger than its predecessor.
        Severity is High when a violation exists. Rows containing NULL step
        values cannot be verified: they do not fail the check, but they are
        reported in ``evidence`` and raise the severity to Medium because they
        mean the funnel is incomplete (usually a lost join row). An empty frame
        passes with "nothing to check".
    """
    func = "check_funnel_monotonicity"
    _require_frame(df, func)
    steps = _require_column_list(step_columns, func, "step_columns", min_len=2)
    _require_columns(df, steps, func)
    for column in steps:
        if not _is_numeric_like(df[column]):
            raise TypeError(
                f"{func}: step column {column!r} must be numeric (a count), got '{df[column].dtype}'. "
                "Cast the counts before validating the funnel."
            )

    rows = int(df.shape[0])
    if rows == 0:
        return _empty_result(
            "funnel_monotonicity",
            "Empty frame: no funnel row to check for monotonicity.",
            evidence={"step_columns": steps, "rows": 0, "violating_rows": 0},
        )

    values = df[steps].astype("float64")
    violations: list[dict[str, Any]] = []
    violating_any = pd.Series(False, index=values.index)
    violating_comparisons = 0
    unverifiable_rows = 0

    for position in range(len(steps) - 1):
        previous_step, current_step = steps[position], steps[position + 1]
        previous_values, current_values = values[previous_step], values[current_step]
        comparable = previous_values.notna() & current_values.notna()
        broken = comparable & (current_values > previous_values)
        unverifiable = ~comparable
        violating_any = violating_any | broken
        violating_comparisons += int(broken.sum())
        unverifiable_rows += int(unverifiable.sum())
        for index in list(values.index[broken])[:5]:
            if len(violations) < 5:
                violations.append(
                    {
                        "row": str(index),
                        "from_step": previous_step,
                        "to_step": current_step,
                        "from_value": float(previous_values.loc[index]),
                        "to_value": float(current_values.loc[index]),
                        "delta": float(current_values.loc[index] - previous_values.loc[index]),
                    }
                )

    violating_rows = int(violating_any.sum())
    violations_truncated = violating_comparisons > len(violations)
    passed = violating_rows == 0
    if not passed:
        severity = Severity.HIGH
    elif unverifiable_rows > 0:
        severity = Severity.MEDIUM
    else:
        severity = Severity.INFORMATIONAL

    if passed and unverifiable_rows == 0:
        message = (
            f"Funnel steps {' > '.join(steps)} are non-increasing for all {rows} row(s): the "
            "steps are properly nested, so conversion rates cannot exceed 100%."
        )
    elif passed:
        message = (
            f"No step grows from its predecessor, but {unverifiable_rows} step comparison(s) "
            "involve a NULL count and could not be verified. A NULL step count usually means a "
            "join lost the row rather than a genuine zero."
        )
    else:
        message = (
            f"{violating_rows} funnel row(s) grow instead of shrink inside an ordered "
            f"session funnel ({violating_comparisons} illegal step comparison(s)). Sessions "
            "reaching a later step are a subset of those reaching the previous step, so this can "
            "only come from how the funnel was built (LEFT JOIN fan-out, non-nested step filters, "
            "steps ordered by the wrong timestamp) and it would show up as a conversion rate "
            "above 100%."
        )

    return CheckResult(
        name="funnel_monotonicity",
        passed=passed,
        severity=severity,
        metric_value=violating_rows,
        threshold=0,
        message=message,
        evidence={
            "step_columns": steps,
            "rows": rows,
            "comparisons": rows * (len(steps) - 1),
            "violating_rows": violating_rows,
            "violating_comparisons": violating_comparisons,
            "unverifiable_comparisons": unverifiable_rows,
            "violations": violations,
            "violations_truncated": violations_truncated,
        },
    )


def check_date_coverage(
    df: pd.DataFrame,
    date_column: str,
    expected_start: Any,
    expected_end: Any,
) -> CheckResult:
    """Detect missing days in a daily series (a gap means a missing data shard).

    GA4 semantics
    -------------
    The export is partitioned by day (``events_YYYYMMDD``). A query that reads
    only the shards that exist, without a calendar spine, silently produces a
    series with holes: a day with no data simply disappears instead of appearing
    as zero. Gaps are easy to miss in a chart and corrupt week-over-week and
    month-over-month comparisons. This check compares the observed days with a
    complete daily calendar between the expected bounds.

    Days observed *outside* the expected window are reported as well: they mean
    the assumed window is wrong, not that the data is wrong.

    Parameters
    ----------
    df:
        Daily aggregate (one row per day, or more if the grain is per segment).
    date_column:
        A ``date``/``datetime``/text column. Numeric date columns (epoch seconds,
        microseconds, or an integer ``YYYYMMDD``) are rejected: the unit would be
        guessed silently, which is exactly the class of bug this library exists
        to prevent.
    expected_start, expected_end:
        Inclusive bounds (``date``, ``datetime`` or ISO string).

    Returns
    -------
    CheckResult
        ``passed`` is ``True`` only when every day in the window is present.
        Severity is High for gaps, Medium when data exists outside the window,
        Informational when the calendar is complete. An empty frame fails with
        every expected day reported missing - an empty daily series over a
        non-empty window is a coverage failure, not a clean result.
    """
    func = "check_date_coverage"
    _require_frame(df, func)
    column = _require_column_name(date_column, func, "date_column")
    _require_columns(df, [column], func)
    start = _to_timestamp(expected_start, func, "expected_start")
    end = _to_timestamp(expected_end, func, "expected_end")
    if start > end:
        raise ValueError(
            f"{func}: expected_start ({start.date().isoformat()}) must not be after "
            f"expected_end ({end.date().isoformat()})"
        )

    series = df[column]
    if _is_numeric_like(series):
        raise TypeError(
            f"{func}: date column {column!r} is numeric ('{series.dtype}'). Numeric dates hide "
            "their unit (epoch seconds, microseconds or YYYYMMDD), so pass a date/datetime or "
            "ISO string column instead."
        )
    try:
        parsed = pd.to_datetime(series, errors="coerce")
    except ValueError as exc:  # e.g. mixed UTC offsets, which pandas refuses to guess
        raise ValueError(f"{func}: {column!r} could not be parsed as a date column: {exc}") from exc
    unparsable = parsed.isna() & series.notna()
    if bool(unparsable.any()):
        raise ValueError(
            f"{func}: {int(unparsable.sum())} value(s) in {column!r} are not parseable as dates, "
            f"e.g. {_sample(series.loc[unparsable].tolist())}"
        )
    parsed = parsed.dt.tz_localize(None) if parsed.dt.tz is not None else parsed
    observed = pd.Index(parsed.dropna().dt.normalize().unique())
    expected = pd.date_range(start=start, end=end, freq="D")
    missing = expected.difference(observed)
    out_of_range = observed.difference(expected)
    rows = int(df.shape[0])

    passed = len(missing) == 0
    if len(missing) > 0:
        severity = Severity.HIGH
    elif len(out_of_range) > 0:
        severity = Severity.MEDIUM
    else:
        severity = Severity.INFORMATIONAL

    if rows == 0:
        message = (
            f"Empty frame: all {len(expected)} day(s) between "
            f"{start.date().isoformat()} and {end.date().isoformat()} are missing from {column!r}, "
            "which is a coverage failure rather than a validated series."
        )
    elif passed and len(out_of_range) == 0:
        message = (
            f"All {len(expected)} day(s) between {start.date().isoformat()} and "
            f"{end.date().isoformat()} are present in {column!r}: the daily series has no gap."
        )
    elif passed:
        message = (
            f"The daily series covers every expected day, but {len(out_of_range)} observed day(s) "
            "fall outside the assumed window - the window assumption is wrong, not the data."
        )
    else:
        message = (
            f"{len(missing)} day(s) are missing from {column!r} between "
            f"{start.date().isoformat()} and {end.date().isoformat()} "
            f"(e.g. {_sample([d.date().isoformat() for d in missing])}). GA4 exports are "
            "partitioned per day, so a hole means the day's shard was never read (query built "
            "from the shards that exist instead of a complete calendar spine) or is absent from "
            "the dataset. Weekly/monthly comparisons across that hole are wrong, not merely "
            "incomplete."
        )

    return CheckResult(
        name="date_coverage",
        passed=passed,
        severity=severity,
        metric_value=len(missing),
        threshold=0,
        message=message,
        evidence={
            "column": column,
            "rows": rows,
            "expected_start": start.date().isoformat(),
            "expected_end": end.date().isoformat(),
            "expected_days": len(expected),
            "observed_days": int(len(observed)),
            "missing_days": len(missing),
            "missing_dates_sample": _sample([d.date().isoformat() for d in missing]),
            "out_of_range_days": len(out_of_range),
            "out_of_range_dates_sample": _sample([d.date().isoformat() for d in out_of_range]),
        },
    )


def micros_to_datetime(series: pd.Series) -> pd.Series:
    """Convert GA4 microsecond timestamps to timezone-aware UTC datetimes.

    The unit trap
    -------------
    ``event_timestamp`` (and ``user_first_touch_timestamp``) are **microseconds**
    since the Unix epoch, as documented by GA4. Unix timestamps in most other
    systems are *seconds* (Python ``time.time()``, BigQuery ``TIMESTAMP_SECONDS``).
    Reading a microsecond value as seconds puts the event around the year 56000;
    reading a seconds value as microseconds puts it in January 1970. Both fail
    loudly in a chart and quietly in a metric, so the conversion belongs in one
    named, tested place.

    Parameters
    ----------
    series:
        Numeric microsecond timestamps (nullable integer dtypes are accepted) or
        a ``datetime64`` column, which is returned normalised to UTC.

    Returns
    -------
    pandas.Series
        ``datetime64[ns, UTC]`` with ``NaT`` where the input was missing.

    Raises
    ------
    TypeError
        If the input is not numeric/datetime, so the caller cannot silently pass
        a string column through the conversion.
    """
    if not isinstance(series, pd.Series):
        raise TypeError(
            f"micros_to_datetime: expected a pandas Series, got {type(series).__name__}"
        )
    if pd.api.types.is_datetime64_any_dtype(series):
        result = series
    else:
        micros = _as_float_series(series, "micros_to_datetime", "the timestamp series")
        result = pd.to_datetime(micros, unit="us", errors="coerce")
    return result.dt.tz_localize("UTC") if result.dt.tz is None else result.dt.tz_convert("UTC")


def check_timestamp_validity(
    df: pd.DataFrame,
    timestamp_column: str = "event_timestamp",
    min_ts: Any = None,
    max_ts: Any = None,
) -> CheckResult:
    """Validate that timestamps sit inside a plausible window, in the right unit.

    GA4 semantics
    -------------
    ``event_timestamp`` is **microseconds** since the Unix epoch. This check
    exists because that unit is the single most common trap in GA4 work: a
    seconds value read as microseconds lands near 1970, a seconds-vs-microseconds
    mix-up breaks every partition filter, and a millisecond value (1/1000 of the
    correct magnitude) lands in 1970 as well. Bounds can be given as microseconds
    (native) or as any date/datetime/ISO string, in which case they are converted
    with the same microsecond unit - see :func:`micros_to_datetime`.

    NULLs are counted as invalid on purpose: ``event_timestamp`` is a required
    GA4 field, so a NULL in the aggregate means an expression produced it (for
    instance ``TIMESTAMP_MICROS(NULL)``), not that the source data lacks a time.

    Parameters
    ----------
    df:
        Any aggregate containing the timestamp column (microsecond integers or a
        ``datetime64`` column produced by ``TIMESTAMP_MICROS``).
    timestamp_column:
        Column to validate.
    min_ts, max_ts:
        Inclusive window; required (their presence is what makes the check
        meaningful). Microseconds or dates.

    Returns
    -------
    CheckResult
        ``passed`` is ``True`` when every row has a non-NULL timestamp inside the
        window. Severity is High otherwise (out-of-window values indicate a unit
        or partition error that invalidates date filtering). An empty frame
        passes with a "nothing to check" message.
    """
    func = "check_timestamp_validity"
    _require_frame(df, func)
    column = _require_column_name(timestamp_column, func, "timestamp_column")
    _require_columns(df, [column], func)
    if min_ts is None or max_ts is None:
        raise ValueError(
            f"{func}: min_ts and max_ts are required - an unbounded timestamp check cannot "
            "detect the unit trap it exists for"
        )
    lower = _to_micros(min_ts, func, "min_ts")
    upper = _to_micros(max_ts, func, "max_ts")
    if lower > upper:
        raise ValueError(
            f"{func}: min_ts ({lower} us) must not be after max_ts ({upper} us)"
        )

    rows = int(df.shape[0])
    if rows == 0:
        return _empty_result(
            "timestamp_validity",
            f"Empty frame: no {column!r} value to validate.",
            evidence={
                "column": column,
                "rows": 0,
                "window_min_micros": lower,
                "window_max_micros": upper,
            },
        )

    micros = _micros_series(df[column], func, f"{column!r}")
    null_count = int(micros.isna().sum())
    below = int((micros < lower).sum())
    above = int((micros > upper).sum())
    above_or_below = below + above
    invalid_rows = above_or_below + null_count
    present = micros.dropna()
    observed_min = float(present.min()) if present.shape[0] else None
    observed_max = float(present.max()) if present.shape[0] else None
    passed = invalid_rows == 0
    severity = Severity.INFORMATIONAL if passed else Severity.HIGH

    if passed:
        message = (
            f"All {rows} {column!r} value(s) fall inside "
            f"[{_iso_from_micros(lower)}, {_iso_from_micros(upper)}] microseconds, with no NULL: "
            "the timestamp column carries the expected GA4 microsecond unit."
        )
    else:
        message = (
            f"{invalid_rows} of {rows} {column!r} value(s) are not plausible: {below} below the "
            f"window, {above} above it, {null_count} NULL. GA4 stores event_timestamp in "
            "MICROSECONDS; values near 1970 or near the year 56000 mean the unit was mixed up "
            "(seconds or milliseconds), and NULL means an expression produced it. Either way, "
            "date filters and partition pruning on this column are unreliable."
        )

    return CheckResult(
        name="timestamp_validity",
        passed=passed,
        severity=severity,
        metric_value=invalid_rows,
        threshold=0,
        message=message,
        evidence={
            "column": column,
            "rows": rows,
            "window_min_micros": lower,
            "window_max_micros": upper,
            "window_min_utc": _iso_from_micros(lower),
            "window_max_utc": _iso_from_micros(upper),
            "observed_min_micros": observed_min,
            "observed_max_micros": observed_max,
            "observed_min_utc": _iso_from_micros(observed_min),
            "observed_max_utc": _iso_from_micros(observed_max),
            "rows_below_window": below,
            "rows_above_window": above,
            "rows_null": null_count,
            "unit": "microseconds since Unix epoch (GA4 native)",
        },
    )


def check_currency_consistency(df: pd.DataFrame, currency_column: str = "currency") -> CheckResult:
    """Flag more than one currency inside a single revenue aggregate.

    GA4 semantics
    -------------
    GA4 keeps two revenue fields: ``purchase_revenue`` (in the currency stored on
    the event) and ``purchase_revenue_in_usd`` (the property-currency amount
    converted to USD). If an aggregate contains events in several currencies and
    only the raw ``purchase_revenue`` is summed, the total adds amounts that are
    not comparable - 100 JPY is not 100 USD - and the error is invisible because
    the column has no unit. Either restrict the aggregate to one currency or sum
    the USD field, and state which one the metric uses.

    Values are compared after trimming and upper-casing (``usd`` and ``USD `` are
    the same currency), and GA4 placeholder values such as ``(not set)`` are
    reported separately instead of being counted as a currency.

    Parameters
    ----------
    df:
        Any aggregate with a per-row currency column.
    currency_column:
        Column holding the ISO currency code.

    Returns
    -------
    CheckResult
        ``passed`` is ``True`` when at most one real currency is present.
        Severity is High when several are present (silently wrong totals).
        An empty frame, or a frame whose currency column is entirely NULL,
        passes with a message saying that no comparison was possible.
    """
    func = "check_currency_consistency"
    _require_frame(df, func)
    column = _require_column_name(currency_column, func, "currency_column")
    _require_columns(df, [column], func)

    rows = int(df.shape[0])
    if rows == 0:
        return _empty_result(
            "currency_consistency",
            f"Empty frame: no {column!r} value to compare.",
            evidence={"column": column, "rows": 0, "distinct_currencies": 0},
        )

    series = df[column]
    missing_mask = _missing_mask(series)
    text = series.astype("string").str.strip()
    placeholder_mask = text.str.lower().isin(GA4_PLACEHOLDERS).fillna(False)
    usable = text.loc[~missing_mask & ~placeholder_mask].str.upper()
    counts = usable.value_counts()
    currencies = [str(c) for c in counts.index]
    currency_counts = {str(k): int(v) for k, v in counts.items()}
    distinct = len(currencies)
    missing_rows = int(missing_mask.sum())
    placeholder_rows = int(placeholder_mask.sum())
    passed = distinct <= 1
    severity = Severity.INFORMATIONAL if passed else Severity.HIGH

    if distinct == 0:
        message = (
            f"No usable {column!r} value in {rows} row(s) ({missing_rows} missing, "
            f"{placeholder_rows} placeholder), so currency comparability could not be verified. "
            "State the currency of any revenue metric built on this aggregate."
        )
    elif passed:
        message = (
            f"One currency ({currencies[0]}) across all {int(usable.shape[0])} row(s) with a "
            "usable currency value: amounts in this aggregate are directly summable. "
            f"{missing_rows} missing / {placeholder_rows} placeholder value(s) ignored."
        )
    else:
        message = (
            f"{distinct} currencies appear in {column!r} ({', '.join(sorted(currencies))}) with "
            f"counts {currency_counts}. Summing a revenue column across them "
            "adds non-comparable amounts (100 JPY is not 100 USD) and the result looks valid. "
            "Filter to one currency or sum the USD-normalised revenue field instead."
        )

    return CheckResult(
        name="currency_consistency",
        passed=passed,
        severity=severity,
        metric_value=distinct,
        threshold=1,
        message=message,
        evidence={
            "column": column,
            "rows": rows,
            "rows_with_usable_currency": int(usable.shape[0]),
            "rows_missing_currency": missing_rows,
            "rows_placeholder_currency": placeholder_rows,
            "distinct_currencies": distinct,
            "currencies": sorted(currencies),
            "currency_counts": currency_counts,
        },
    )


def check_revenue_null_rate(
    df: pd.DataFrame,
    *revenue_columns: str,
    max_null_rate: float = 0.0,
) -> CheckResult:
    """Report how complete each revenue column is, and why NULLs are expected.

    GA4 semantics
    -------------
    ``purchase_revenue`` is filled only when the purchase event carries a value
    and it is expressed in the event currency. When a store's currency differs
    from the GA4 property currency, or when a purchase event arrives without
    revenue parameters, ``purchase_revenue`` is legitimately NULL while
    ``purchase_revenue_in_usd`` still holds the converted amount (or vice versa
    for manual/offline events). A NULL is therefore not corruption - but it must
    be quantified, because any metric that silently treats NULL as 0 understates
    revenue, and any metric that divides by row count dilutes its average.

    Parameters
    ----------
    df:
        Any aggregate containing the revenue columns (they must be numeric).
    *revenue_columns:
        Column names to inspect, e.g. ``"purchase_revenue"``,
        ``"purchase_revenue_in_usd"``. At least one is required.
    max_null_rate:
        Tolerance in ``[0, 1]`` applied to every column. Default ``0.0``.

    Returns
    -------
    CheckResult
        ``passed`` is ``True`` when every column's NULL rate is within tolerance.
        ``metric_value`` is the worst observed rate across the columns (a single
        number to render). Severity is High when a column is 100% NULL (it
        carries no information at all and silently yields 0 in a SUM), Medium
        when it is partially NULL, Informational when complete.
    """
    func = "check_revenue_null_rate"
    _require_frame(df, func)
    if not revenue_columns:
        raise ValueError(
            f"{func}: pass at least one revenue column, e.g. "
            'check_revenue_null_rate(df, "purchase_revenue", "purchase_revenue_in_usd")'
        )
    columns = [_require_column_name(c, func, f"revenue_columns[{i}]") for i, c in enumerate(revenue_columns)]
    _require_columns(df, columns, func)
    tolerance = _require_rate(max_null_rate, func, "max_null_rate")
    for column in columns:
        if not _is_numeric_like(df[column]):
            raise TypeError(
                f"{func}: revenue column {column!r} must be numeric, got '{df[column].dtype}'. "
                "Count rows in SQL instead of casting revenue to text."
            )

    rows = int(df.shape[0])
    if rows == 0:
        return _empty_result(
            "revenue_null_rate",
            f"Empty frame: no revenue row to measure for {columns}.",
            evidence={"columns": columns, "rows": 0, "null_rates": {c: 0.0 for c in columns}},
        )

    details: dict[str, dict[str, Any]] = {}
    worst_rate = 0.0
    any_complete = False
    for column in columns:
        series = df[column]
        null_rows = int(series.isna().sum())
        rate = null_rows / rows
        worst_rate = max(worst_rate, rate)
        if rate == 0.0:
            any_complete = True
        non_null = series.dropna()
        details[column] = {
            "rows": rows,
            "null_rows": null_rows,
            "null_rate": round(rate, 6),
            "non_null_rows": int(non_null.shape[0]),
            "observed_sum": float(non_null.sum()) if non_null.shape[0] else None,
        }

    passed = worst_rate <= tolerance
    fully_null = [column for column, detail in details.items() if detail["null_rows"] == rows]
    if fully_null:
        severity = Severity.HIGH
    elif not passed:
        severity = Severity.MEDIUM
    else:
        severity = Severity.INFORMATIONAL

    if passed:
        message = (
            f"All {rows} row(s) carry a non-NULL value for {columns}: revenue metrics can use "
            "every row without an imputation rule."
        )
    elif fully_null:
        message = (
            f"{fully_null} is NULL in every one of the {rows} row(s): a SUM over it returns 0 "
            "silently, which reads as 'no revenue' rather than 'no data'. In GA4 this happens "
            "legitimately when the store currency differs from the property currency (the "
            "converted purchase_revenue_in_usd field stays populated) or when transactions are "
            "imported manually; the metric must therefore state which revenue field it uses."
        )
    else:
        message = (
            f"Revenue columns are incompletely populated (worst rate {worst_rate:.2%}): "
            + ", ".join(
                f"{column}={detail['null_rate']:.2%} NULL" for column, detail in details.items()
            )
            + ". A partial NULL rate in purchase_revenue is EXPECTED GA4 behaviour when the "
            "event currency differs from the property currency - it is not corruption, but a "
            "metric that treats NULL as 0 understates revenue and a mean over rows understates "
            "the order value. Document which field is used and how NULLs are handled."
            + ("" if any_complete else " No revenue column in this aggregate is complete.")
        )

    return CheckResult(
        name="revenue_null_rate",
        passed=passed,
        severity=severity,
        metric_value=round(worst_rate, 6),
        threshold=tolerance,
        message=message,
        evidence={
            "columns": columns,
            "rows": rows,
            "worst_null_rate": round(worst_rate, 6),
            "fully_null_columns": fully_null,
            "per_column": details,
        },
    )


def check_session_id_reuse(
    df: pd.DataFrame,
    session_id_column: str = "ga_session_id",
    user_id_column: str = "user_pseudo_id",
    expect_reuse: bool = True,
) -> CheckResult:
    """Measure how often one ``ga_session_id`` value maps to several users.

    GA4 semantics
    -------------
    ``ga_session_id`` is a timestamp-derived integer that GA4 writes on the first
    event of a session **together with** ``user_pseudo_id``. It is unique per
    user, not globally: two different users can start sessions in the same second
    and land on the same integer. The true session key is the composite
    ``(user_pseudo_id, ga_session_id)``. Any join, de-duplication or session
    filter keyed on ``ga_session_id`` alone therefore merges unrelated sessions -
    the kind of bug that produces "a session with two entry pages" and quietly
    corrupts entry-channel attribution.

    Pass semantics (documented deliberately)
    ----------------------------------------
    ``passed`` means *"the observation matches the documented GA4 expectation"*,
    **not** "the data is clean". With the default ``expect_reuse=True`` the check
    passes when reuse *is* observed (which confirms the composite-key
    requirement) and fails when no reuse is observed, because then the composite
    key claim cannot be demonstrated from this aggregate (usually because the
    sample is too small or the query already de-duplicated by the composite key).
    With ``expect_reuse=False`` - for a pipeline that explicitly assumes
    ``ga_session_id`` is globally unique - the check passes only when no reuse is
    observed, and reuse raises the severity to High because the pipeline's
    uniqueness assumption is false.

    Rows missing either id are excluded from the measurement (they cannot be
    attributed) and reported.

    Returns
    -------
    CheckResult
        Severity: Informational when the observation matches the expectation,
        High when an explicit uniqueness assumption is violated, Medium when
        reuse was expected but not observed. An empty frame passes with zero
        measurements.
    """
    func = "check_session_id_reuse"
    _require_frame(df, func)
    session_column = _require_column_name(session_id_column, func, "session_id_column")
    user_column = _require_column_name(user_id_column, func, "user_id_column")
    _require_columns(df, [session_column, user_column], func)
    if not isinstance(expect_reuse, bool):
        raise TypeError(f"{func}: expect_reuse must be a bool, got {type(expect_reuse).__name__}")

    rows = int(df.shape[0])
    if rows == 0:
        return _empty_result(
            "session_id_reuse",
            f"Empty frame: no {session_column!r} value to test for cross-user reuse.",
            evidence={"session_id_column": session_column, "user_id_column": user_column, "rows": 0},
        )

    incomplete = _missing_mask(df[session_column]) | _missing_mask(df[user_column])
    usable = df.loc[~incomplete, [session_column, user_column]]
    excluded_rows = int(incomplete.sum())

    if usable.shape[0] == 0:
        return CheckResult(
            name="session_id_reuse",
            passed=False,
            severity=Severity.MEDIUM,
            metric_value=None,
            threshold=None,
            message=(
                f"No row has both {session_column!r} and {user_column!r}, so cross-user reuse of "
                "the session id could not be measured from this aggregate."
            ),
            evidence={
                "session_id_column": session_column,
                "user_id_column": user_column,
                "rows": rows,
                "rows_excluded_missing_ids": excluded_rows,
                "reused_session_ids": 0,
                "expect_reuse": expect_reuse,
            },
        )

    users_per_session = usable.groupby(session_column, dropna=True, observed=True)[
        user_column
    ].nunique()
    reused = users_per_session[users_per_session > 1]
    reused_ids = int(reused.shape[0])
    max_users_per_session = int(users_per_session.max()) if users_per_session.shape[0] else 0
    reused_rows = int(usable[session_column].isin(reused.index).sum())
    reuse_observed = reused_ids > 0
    passed = reuse_observed == expect_reuse

    if not passed and expect_reuse:
        severity = Severity.MEDIUM
    elif not passed:
        severity = Severity.HIGH
    else:
        severity = Severity.INFORMATIONAL

    if reuse_observed and expect_reuse:
        message = (
            f"{reused_ids} of {int(users_per_session.shape[0])} {session_column!r} value(s) appear "
            f"for more than one {user_column!r} (up to {max_users_per_session} users share one "
            f"id; {reused_rows} of {rows} rows involved). This is the documented GA4 behaviour "
            "that makes the composite (user_pseudo_id, ga_session_id) key necessary - it is not "
            "corruption. PASS here means 'reuse observed as expected', not 'the data is clean': "
            "any join or de-duplication keyed on ga_session_id alone is incorrect."
        )
    elif not reuse_observed and expect_reuse:
        message = (
            f"No {session_column!r} value is shared by two {user_column!r} values in this "
            "aggregate, so the composite-key claim could not be demonstrated from it. That is "
            "expected in a very small sample or in an aggregate already grouped by the composite "
            "key; it is not evidence that ga_session_id is globally unique."
        )
    elif reuse_observed:
        message = (
            f"The pipeline expects {session_column!r} to be unique, but {reused_ids} value(s) are "
            f"shared by more than one {user_column!r} (up to {max_users_per_session} users). The "
            "uniqueness assumption is false, so any join keyed on the session id alone merges "
            "unrelated sessions and corrupts session counts and attribution."
        )
    else:
        message = (
            f"No cross-user reuse of {session_column!r} observed, matching the uniqueness this "
            "caller assumed."
        )

    return CheckResult(
        name="session_id_reuse",
        passed=passed,
        severity=severity,
        metric_value=reused_ids,
        threshold=None if expect_reuse else 0,
        message=message,
        evidence={
            "session_id_column": session_column,
            "user_id_column": user_column,
            "rows": rows,
            "rows_measured": int(usable.shape[0]),
            "rows_excluded_missing_ids": excluded_rows,
            "distinct_session_ids": int(users_per_session.shape[0]),
            "distinct_users": int(usable[user_column].nunique()),
            "reused_session_ids": reused_ids,
            "max_users_per_session_id": max_users_per_session,
            "rows_on_reused_session_ids": reused_rows,
            "sample_reused_session_ids": _sample(list(reused.index)),
            "expect_reuse": expect_reuse,
            "pass_means": (
                "observed reuse matches the documented GA4 expectation"
                if expect_reuse
                else "no reuse observed, matching the caller's uniqueness assumption"
            ),
        },
    )


def check_share_bounds(
    df: pd.DataFrame,
    column: str,
    low: float = 0.0,
    high: float = 1.0,
) -> CheckResult:
    """Guard that a share/rate column stays inside its legal range.

    Semantics
    ---------
    A rate column (conversion rate, share of sessions, bounce rate) is a ratio
    whose value must lie in ``[0, 1]``. A value above 1 means the denominator is
    wrong - typically a numerator counted over a wider grain than the denominator
    (sessions in the numerator, users in the denominator), a fan-out join, or a
    share computed before filtering. A negative value usually means two
    aggregates were subtracted in the wrong order. Both produce a metric that
    still *looks* plausible on a dashboard, which is why the guard belongs in the
    pipeline rather than in a reviewer's head.

    Missing values are counted but do not fail the check: a NULL share is an
    incomplete row, not an impossible value (its impact is a coverage question).

    Parameters
    ----------
    df:
        Any aggregate containing the rate column.
    column:
        Numeric rate column.
    low, high:
        Inclusive bounds, defaulting to ``[0.0, 1.0]``. Pass e.g. ``high=100.0``
        when the column is stored as a percentage instead of a fraction.

    Returns
    -------
    CheckResult
        ``passed`` is ``True`` when no value falls outside the bounds. Severity is
        High when a value is out of range (the definition of the metric is
        wrong). An empty frame passes with a 0.0 measurement.
    """
    func = "check_share_bounds"
    _require_frame(df, func)
    name = _require_column_name(column, func, "column")
    _require_columns(df, [name], func)
    if isinstance(low, bool) or isinstance(high, bool) or not isinstance(
        low, (int, float, np.integer, np.floating)
    ) or not isinstance(high, (int, float, np.integer, np.floating)):
        raise TypeError(f"{func}: low and high must be numbers, got {type(low).__name__}/{type(high).__name__}")
    lower, upper = float(low), float(high)
    if lower > upper:
        raise ValueError(f"{func}: low ({lower}) must not be greater than high ({upper})")
    if not _is_numeric_like(df[name]):
        raise TypeError(
            f"{func}: share column {name!r} must be numeric, got '{df[name].dtype}'. "
            "A rate stored as text cannot be validated."
        )

    rows = int(df.shape[0])
    if rows == 0:
        return _empty_result(
            "share_bounds",
            f"Empty frame: no {name!r} value to validate against [{lower}, {upper}].",
            evidence={"column": name, "rows": 0, "low": lower, "high": upper},
        )

    values = _as_float_series(df[name], func, f"{name!r}")
    missing_count = int(values.isna().sum())
    out_of_bounds = ((values < lower) | (values > upper)).fillna(False)
    out_of_bounds_count = int(out_of_bounds.sum())
    present = values.dropna()
    passed = out_of_bounds_count == 0
    severity = Severity.INFORMATIONAL if passed else Severity.HIGH

    if passed:
        message = (
            f"All {int(present.shape[0])} non-NULL {name!r} value(s) lie inside "
            f"[{lower}, {upper}]; {missing_count} NULL value(s) were not evaluated."
        )
    else:
        message = (
            f"{out_of_bounds_count} value(s) of {name!r} fall outside [{lower}, {upper}] "
            f"(observed range {float(present.min()):.6g} to {float(present.max()):.6g}), e.g. rows "
            f"{_sample(list(values.index[out_of_bounds]))}. A rate outside its legal range means "
            "the numerator and the denominator were computed over different populations or grains "
            "- the metric must be recomputed, not clipped, because clipping hides the bug."
        )

    return CheckResult(
        name="share_bounds",
        passed=passed,
        severity=severity,
        metric_value=out_of_bounds_count,
        threshold=0,
        message=message,
        evidence={
            "column": name,
            "rows": rows,
            "values_checked": int(present.shape[0]),
            "null_values": missing_count,
            "low": lower,
            "high": upper,
            "observed_min": float(present.min()) if present.shape[0] else None,
            "observed_max": float(present.max()) if present.shape[0] else None,
            "out_of_bounds_values": out_of_bounds_count,
            "out_of_bounds_rows_sample": _sample(list(values.index[out_of_bounds])),
        },
    )
