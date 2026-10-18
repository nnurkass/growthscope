"""Tests for :mod:`growthscope.quality.checks`.

Every frame used here comes from ``tests/conftest.py`` and is **SYNTHETIC**
(hand-written) - see ``tests/fixtures/README.md``. The assertions verify the
behaviour of the *code*, never a fact about the GA4 sample dataset.

Coverage per check: a passing case, a failing case, and the error contract
(missing column -> ``ValueError``, wrong dtype/argument type -> ``TypeError``,
empty frame -> graceful result with no exception).
"""

from __future__ import annotations

import dataclasses
import json
from datetime import date, datetime, timezone

import pandas as pd
import pytest

from growthscope.quality import (
    CheckResult,
    Severity,
    check_currency_consistency,
    check_date_coverage,
    check_duplicate_composite_key,
    check_funnel_monotonicity,
    check_no_null_identifiers,
    check_purchase_transaction_duplicates,
    check_revenue_null_rate,
    check_session_id_reuse,
    check_share_bounds,
    check_timestamp_validity,
    micros_to_datetime,
)

FUNNEL_STEPS = [
    "step_1_view_item",
    "step_2_add_to_cart",
    "step_3_begin_checkout",
    "step_4_add_payment_info",
    "step_5_purchase",
]

# 2021-01-01T00:00:00Z and 2021-02-01T00:00:00Z expressed in GA4 microseconds.
JANUARY_2021_START_MICROS = 1_609_459_200_000_000
FEBRUARY_2021_START_MICROS = 1_612_137_600_000_000


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


class TestCheckResultModel:
    """The result object must stay immutable, serialisable and self-describing."""

    def test_severity_values_are_lowercase_strings(self) -> None:
        assert Severity.HIGH.value == "high"
        assert Severity.CRITICAL.value == "critical"
        assert set(severity.value for severity in Severity) == {
            "informational",
            "low",
            "medium",
            "high",
            "critical",
        }

    def test_check_result_is_frozen(self, syn_clean_session_df: pd.DataFrame) -> None:
        result = check_no_null_identifiers(syn_clean_session_df)
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.passed = False  # type: ignore[misc]

    @pytest.mark.parametrize("check_name", ["no_null_identifiers", "share_bounds"])
    def test_to_dict_is_json_serialisable(self, syn_share_df: pd.DataFrame, check_name: str) -> None:
        result = (
            check_no_null_identifiers(syn_share_df, id_column="conversion_rate")
            if check_name == "no_null_identifiers"
            else check_share_bounds(syn_share_df, "conversion_rate")
        )
        payload = json.loads(json.dumps(result.to_dict()))
        assert payload["name"] == check_name
        assert payload["severity"] in {severity.value for severity in Severity}
        assert isinstance(payload["evidence"], dict)


# ---------------------------------------------------------------------------
# 1. missing identifiers
# ---------------------------------------------------------------------------


class TestCheckNoNullIdentifiers:
    """GA4 pseudonymous ids can be missing; the rate must be reported, not hidden."""

    def test_all_ids_present_passes(self, syn_clean_session_df: pd.DataFrame) -> None:
        result = check_no_null_identifiers(syn_clean_session_df)
        assert result.passed is True
        assert result.severity is Severity.INFORMATIONAL
        assert result.metric_value == 0.0
        assert result.evidence["missing_rows"] == 0

    def test_missing_id_is_reported_as_rate(self, syn_session_df: pd.DataFrame) -> None:
        result = check_no_null_identifiers(syn_session_df)
        assert result.passed is False
        assert result.severity is Severity.HIGH
        assert result.evidence["rows"] == 6
        assert result.evidence["missing_rows"] == 1
        assert result.metric_value == pytest.approx(1 / 6, abs=1e-6)
        assert result.threshold == 0.0

    def test_message_separates_expectation_from_corruption(self, syn_session_df: pd.DataFrame) -> None:
        message = check_no_null_identifiers(syn_session_df).message.lower()
        assert "expected" in message
        assert "not data corruption" in message
        assert "consent" in message

    def test_whitespace_only_id_counts_as_missing(self, syn_missing_key_df: pd.DataFrame) -> None:
        result = check_no_null_identifiers(syn_missing_key_df, max_missing_rate=1.0)
        assert result.evidence["missing_rows"] == 3
        assert result.metric_value == pytest.approx(1.0)

    def test_tolerance_is_respected(self, syn_session_df: pd.DataFrame) -> None:
        result = check_no_null_identifiers(syn_session_df, max_missing_rate=0.2)
        assert result.passed is True
        assert result.severity is Severity.INFORMATIONAL
        assert result.threshold == 0.2

    def test_empty_frame_is_handled(self) -> None:
        empty = pd.DataFrame({"user_pseudo_id": pd.Series([], dtype="string")})
        result = check_no_null_identifiers(empty)
        assert result.passed is True
        assert result.evidence["rows"] == 0

    def test_missing_column_raises_value_error(self, syn_clean_session_df: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match="not found in the DataFrame"):
            check_no_null_identifiers(syn_clean_session_df, id_column="no_such_column")

    def test_non_dataframe_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="expected a pandas DataFrame"):
            check_no_null_identifiers([{"user_pseudo_id": "u1"}])  # type: ignore[arg-type]

    def test_non_string_column_raises_type_error(self, syn_clean_session_df: pd.DataFrame) -> None:
        with pytest.raises(TypeError, match="must be a string"):
            check_no_null_identifiers(syn_clean_session_df, id_column=1)  # type: ignore[arg-type]

    @pytest.mark.parametrize("tolerance", [1.5, -0.01])
    def test_out_of_range_tolerance_raises_value_error(
        self, syn_clean_session_df: pd.DataFrame, tolerance: float
    ) -> None:
        with pytest.raises(ValueError, match="between 0.0 and 1.0"):
            check_no_null_identifiers(syn_clean_session_df, max_missing_rate=tolerance)

    def test_non_numeric_tolerance_raises_type_error(self, syn_clean_session_df: pd.DataFrame) -> None:
        with pytest.raises(TypeError, match="must be a number"):
            check_no_null_identifiers(syn_clean_session_df, max_missing_rate="0.1")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 2. duplicated composite key
# ---------------------------------------------------------------------------


class TestCheckDuplicateCompositeKey:
    """Repeated events are fine; repeated key rows in an aggregate are not."""

    def test_unique_keys_pass(self, syn_clean_session_df: pd.DataFrame) -> None:
        result = check_duplicate_composite_key(
            syn_clean_session_df, ["user_pseudo_id", "ga_session_id"]
        )
        assert result.passed is True
        assert result.severity is Severity.INFORMATIONAL
        assert result.evidence["duplicate_groups"] == 0
        assert result.evidence["duplicate_rows"] == 0

    def test_duplicate_session_rows_are_flagged(self, syn_session_df: pd.DataFrame) -> None:
        result = check_duplicate_composite_key(
            syn_session_df, ["user_pseudo_id", "ga_session_id"]
        )
        assert result.passed is False
        assert result.severity is Severity.HIGH
        assert result.evidence["duplicate_groups"] == 1
        assert result.evidence["duplicate_rows"] == 2
        assert result.evidence["sample_duplicate_keys"] == ["u1 | 1001"]

    def test_message_explains_events_versus_aggregate_key(self, syn_session_df: pd.DataFrame) -> None:
        message = check_duplicate_composite_key(
            syn_session_df, ["user_pseudo_id", "ga_session_id"]
        ).message
        assert "Repeated *events* are legitimate in GA4" in message
        assert "grain" in message

    def test_incomplete_keys_are_excluded_and_counted(self, syn_session_df: pd.DataFrame) -> None:
        result = check_duplicate_composite_key(
            syn_session_df, ["user_pseudo_id", "ga_session_id"]
        )
        assert result.evidence["rows_excluded_incomplete_key"] == 1
        assert result.evidence["rows_with_complete_key"] == 5

    def test_single_column_key_is_supported(self, syn_session_df: pd.DataFrame) -> None:
        # "u1" and "u2" each appear twice in the synthetic session frame.
        result = check_duplicate_composite_key(syn_session_df, ["user_pseudo_id"])
        assert result.passed is False
        assert result.evidence["duplicate_groups"] == 2
        assert result.evidence["duplicate_rows"] == 4
        assert result.evidence["sample_duplicate_keys"] == ["u1", "u2"]

    def test_frame_without_a_complete_key_passes_but_warns(self, syn_missing_key_df: pd.DataFrame) -> None:
        result = check_duplicate_composite_key(
            syn_missing_key_df, ["user_pseudo_id", "ga_session_id"]
        )
        assert result.passed is True
        assert result.severity is Severity.MEDIUM
        assert "key-coverage problem" in result.message

    def test_empty_frame_is_handled(self) -> None:
        empty = pd.DataFrame(
            {"user_pseudo_id": pd.Series([], dtype="string"), "ga_session_id": pd.Series([], dtype="int64")}
        )
        result = check_duplicate_composite_key(empty, ["user_pseudo_id", "ga_session_id"])
        assert result.passed is True
        assert result.evidence["rows"] == 0

    def test_missing_column_raises_value_error(self, syn_session_df: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match="not found in the DataFrame"):
            check_duplicate_composite_key(syn_session_df, ["user_pseudo_id", "session_id"])

    def test_bare_string_key_columns_raise_type_error(self, syn_session_df: pd.DataFrame) -> None:
        with pytest.raises(TypeError, match="sequence of column names"):
            check_duplicate_composite_key(syn_session_df, "user_pseudo_id")  # type: ignore[arg-type]

    def test_set_of_key_columns_raises_type_error(self, syn_session_df: pd.DataFrame) -> None:
        with pytest.raises(TypeError, match="not a set"):
            check_duplicate_composite_key(syn_session_df, {"user_pseudo_id"})  # type: ignore[arg-type]

    def test_empty_key_columns_raise_value_error(self, syn_session_df: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match="at least 1 column name"):
            check_duplicate_composite_key(syn_session_df, [])


# ---------------------------------------------------------------------------
# 3. purchase transaction duplicates
# ---------------------------------------------------------------------------


class TestCheckPurchaseTransactionDuplicates:
    """A repeated transaction_id repeats its revenue and double-counts money."""

    def test_unique_transactions_pass(self, syn_purchase_clean_df: pd.DataFrame) -> None:
        result = check_purchase_transaction_duplicates(syn_purchase_clean_df)
        assert result.passed is True
        assert result.severity is Severity.INFORMATIONAL
        assert result.metric_value == 0
        assert result.evidence["rows_with_transaction_id"] == 3

    def test_duplicate_transaction_is_flagged(self, syn_purchase_df: pd.DataFrame) -> None:
        result = check_purchase_transaction_duplicates(syn_purchase_df)
        assert result.passed is False
        assert result.severity is Severity.HIGH
        assert result.evidence["duplicate_transaction_ids"] == 1
        assert result.evidence["duplicate_rows"] == 2
        assert result.evidence["sample_duplicate_ids"] == ["T-1001"]
        assert "de-duplicated by transaction_id" in result.message
        assert "counted twice" in result.message

    def test_null_and_empty_ids_are_not_duplicate_groups(self, syn_purchase_df: pd.DataFrame) -> None:
        result = check_purchase_transaction_duplicates(syn_purchase_df)
        assert result.evidence["rows_missing_transaction_id"] == 2
        # Two distinct non-missing ids remain: only T-1001 is duplicated.
        assert result.evidence["rows_with_transaction_id"] == 3
        assert result.evidence["duplicate_transaction_ids"] == 1

    def test_frame_with_only_missing_ids_passes_with_medium_severity(self) -> None:
        frame = pd.DataFrame({"transaction_id": [None, "", None]})
        result = check_purchase_transaction_duplicates(frame)
        assert result.passed is True
        assert result.severity is Severity.MEDIUM
        assert "nothing can be de-duplicated" in result.message
        assert "double-counting risk" in result.message

    @pytest.mark.parametrize("placeholder", ["(not set)", "(not provided)", "NULL"])
    def test_placeholder_ids_are_treated_as_missing(self, placeholder: str) -> None:
        frame = pd.DataFrame({"transaction_id": [placeholder, placeholder, "T-1"]})
        result = check_purchase_transaction_duplicates(frame)
        assert result.passed is True
        assert result.evidence["duplicate_transaction_ids"] == 0
        assert result.evidence["rows_missing_transaction_id"] == 2

    def test_numeric_transaction_ids_are_supported(self) -> None:
        frame = pd.DataFrame({"transaction_id": [11, 11, 12]})
        result = check_purchase_transaction_duplicates(frame)
        assert result.passed is False
        assert result.evidence["sample_duplicate_ids"] == ["11"]

    def test_empty_frame_is_handled(self) -> None:
        empty = pd.DataFrame({"transaction_id": pd.Series([], dtype="string")})
        result = check_purchase_transaction_duplicates(empty)
        assert result.passed is True
        assert result.evidence["rows"] == 0

    def test_missing_column_raises_value_error(self, syn_purchase_df: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match="not found in the DataFrame"):
            check_purchase_transaction_duplicates(syn_purchase_df, transaction_id_column="tid")

    def test_non_string_column_raises_type_error(self, syn_purchase_df: pd.DataFrame) -> None:
        with pytest.raises(TypeError, match="must be a string"):
            check_purchase_transaction_duplicates(syn_purchase_df, transaction_id_column=None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 4. funnel monotonicity
# ---------------------------------------------------------------------------


class TestCheckFunnelMonotonicity:
    """A nested session funnel can never grow from one step to the next."""

    def test_monotonic_funnel_passes(self, syn_funnel_monotonic_df: pd.DataFrame) -> None:
        result = check_funnel_monotonicity(syn_funnel_monotonic_df, FUNNEL_STEPS)
        assert result.passed is True
        assert result.severity is Severity.INFORMATIONAL
        assert result.metric_value == 0
        assert result.evidence["comparisons"] == 4
        assert result.evidence["violations"] == []

    def test_growing_step_is_flagged(self, syn_funnel_non_monotonic_df: pd.DataFrame) -> None:
        result = check_funnel_monotonicity(syn_funnel_non_monotonic_df, FUNNEL_STEPS)
        assert result.passed is False
        assert result.severity is Severity.HIGH
        assert result.metric_value == 1
        violation = result.evidence["violations"][0]
        assert violation["from_step"] == "step_2_add_to_cart"
        assert violation["to_step"] == "step_3_begin_checkout"
        assert violation["from_value"] == 600.0
        assert violation["to_value"] == 650.0
        assert violation["delta"] == 50.0

    def test_violations_are_counted_per_row(self, syn_funnel_mixed_df: pd.DataFrame) -> None:
        result = check_funnel_monotonicity(syn_funnel_mixed_df, FUNNEL_STEPS)
        assert result.evidence["rows"] == 2
        assert result.evidence["violating_rows"] == 1
        assert result.evidence["violations"][0]["row"] == "segment_b"

    def test_equal_steps_are_allowed(self) -> None:
        frame = pd.DataFrame({"step_1": [10, 5], "step_2": [10, 5]})
        result = check_funnel_monotonicity(frame, ["step_1", "step_2"])
        assert result.passed is True
        assert result.severity is Severity.INFORMATIONAL

    def test_null_step_is_reported_as_unverifiable(self, syn_funnel_with_null_df: pd.DataFrame) -> None:
        result = check_funnel_monotonicity(syn_funnel_with_null_df, FUNNEL_STEPS)
        assert result.passed is True
        assert result.severity is Severity.MEDIUM
        assert result.evidence["unverifiable_comparisons"] == 2
        assert "NULL step count" in result.message

    def test_empty_frame_is_handled(self) -> None:
        empty = pd.DataFrame({"step_1": pd.Series([], dtype="int64"), "step_2": pd.Series([], dtype="int64")})
        result = check_funnel_monotonicity(empty, ["step_1", "step_2"])
        assert result.passed is True
        assert result.evidence["rows"] == 0

    def test_single_step_column_raises_value_error(self, syn_funnel_monotonic_df: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match="at least 2 column name"):
            check_funnel_monotonicity(syn_funnel_monotonic_df, ["step_1_view_item"])

    def test_missing_column_raises_value_error(self, syn_funnel_monotonic_df: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match="not found in the DataFrame"):
            check_funnel_monotonicity(syn_funnel_monotonic_df, ["step_1_view_item", "step_99"])

    def test_text_step_column_raises_type_error(self, syn_text_numbers_df: pd.DataFrame) -> None:
        frame = pd.DataFrame({"step_1": ["10", "20"], "step_2": ["5", "4"]})
        with pytest.raises(TypeError, match="must be numeric"):
            check_funnel_monotonicity(frame, ["step_1", "step_2"])
        assert not syn_text_numbers_df.empty  # fixture is available for dtype-error tests

    def test_bare_string_steps_raise_type_error(self, syn_funnel_monotonic_df: pd.DataFrame) -> None:
        with pytest.raises(TypeError, match="sequence of column names"):
            check_funnel_monotonicity(syn_funnel_monotonic_df, "step_1_view_item")  # type: ignore[arg-type]

    def test_non_dataframe_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="expected a pandas DataFrame"):
            check_funnel_monotonicity(None, ["a", "b"])  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 5. date coverage
# ---------------------------------------------------------------------------


class TestCheckDateCoverage:
    """A hole in a daily series means an unread export shard, not a zero day."""

    def test_complete_window_passes(self, syn_clean_session_df: pd.DataFrame) -> None:
        result = check_date_coverage(
            syn_clean_session_df, "session_date", "2021-01-01", "2021-01-04"
        )
        assert result.passed is True
        assert result.severity is Severity.INFORMATIONAL
        assert result.evidence["expected_days"] == 4
        assert result.evidence["observed_days"] == 4

    def test_missing_day_is_detected(self, syn_daily_df: pd.DataFrame) -> None:
        result = check_date_coverage(syn_daily_df, "event_date", "2021-01-01", "2021-01-05")
        assert result.passed is False
        assert result.severity is Severity.HIGH
        assert result.metric_value == 1
        assert result.evidence["missing_dates_sample"] == ["2021-01-03"]
        assert result.evidence["observed_days"] == 4
        assert "shard" in result.message

    def test_accepts_date_objects(self, syn_daily_df: pd.DataFrame) -> None:
        result = check_date_coverage(
            syn_daily_df, "event_date", date(2021, 1, 1), datetime(2021, 1, 5, 12, 0, tzinfo=timezone.utc)
        )
        assert result.evidence["missing_days"] == 1

    def test_out_of_range_day_warns_but_does_not_fail(self, syn_daily_df: pd.DataFrame) -> None:
        extended = pd.concat(
            [syn_daily_df, pd.DataFrame({"event_date": pd.to_datetime(["2021-01-10"]), "sessions": [7]})],
            ignore_index=True,
        )
        result = check_date_coverage(extended, "event_date", "2021-01-01", "2021-01-05")
        assert result.passed is False  # 2021-01-03 is still missing in this window
        assert result.evidence["out_of_range_days"] == 1
        assert result.evidence["out_of_range_dates_sample"] == ["2021-01-10"]

        complete = pd.concat(
            [syn_daily_df, pd.DataFrame({"event_date": pd.to_datetime(["2021-01-03", "2021-01-10"]), "sessions": [5, 7]})],
            ignore_index=True,
        )
        result = check_date_coverage(complete, "event_date", "2021-01-01", "2021-01-05")
        assert result.passed is True
        assert result.severity is Severity.MEDIUM

    def test_empty_frame_reports_every_day_missing(self) -> None:
        empty = pd.DataFrame({"event_date": pd.to_datetime([]), "sessions": pd.Series([], dtype="int64")})
        result = check_date_coverage(empty, "event_date", "2021-01-01", "2021-01-05")
        assert result.passed is False
        assert result.severity is Severity.HIGH
        assert result.evidence["rows"] == 0
        assert result.evidence["missing_days"] == 5

    def test_duplicate_days_do_not_break_coverage(self, syn_daily_df: pd.DataFrame) -> None:
        segmented = pd.concat([syn_daily_df, syn_daily_df], ignore_index=True)
        result = check_date_coverage(segmented, "event_date", "2021-01-01", "2021-01-05")
        assert result.evidence["missing_days"] == 1  # still only 2021-01-03
        assert result.evidence["rows"] == 8

    def test_unparsable_date_raises_value_error(self, syn_daily_df: pd.DataFrame) -> None:
        broken = pd.concat(
            [syn_daily_df, pd.DataFrame({"event_date": ["not-a-date"], "sessions": [1]})],
            ignore_index=True,
        )
        with pytest.raises(ValueError, match="not parseable as dates"):
            check_date_coverage(broken, "event_date", "2021-01-01", "2021-01-05")

    def test_numeric_date_column_raises_type_error(self) -> None:
        frame = pd.DataFrame({"event_date": [20210101, 20210102], "sessions": [1, 2]})
        with pytest.raises(TypeError, match="is numeric"):
            check_date_coverage(frame, "event_date", "2021-01-01", "2021-01-02")

    def test_mixed_timezone_offsets_raise_value_error(self) -> None:
        # pandas refuses to guess a common timezone for mixed UTC offsets, and so
        # does this check: guessing would silently move events between days.
        frame = pd.DataFrame(
            {
                "event_date": ["2021-01-01T00:00:00+01:00", "2021-01-02T00:00:00+02:00"],
                "sessions": [1, 2],
            }
        )
        with pytest.raises(ValueError, match="could not be parsed as a date column"):
            check_date_coverage(frame, "event_date", "2021-01-01", "2021-01-02")

    def test_reversed_window_raises_value_error(self, syn_daily_df: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match="must not be after"):
            check_date_coverage(syn_daily_df, "event_date", "2021-01-05", "2021-01-01")

    def test_unparsable_window_raises_value_error(self, syn_daily_df: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match="could not be parsed"):
            check_date_coverage(syn_daily_df, "event_date", "yesterday", "2021-01-05")

    def test_none_window_raises_value_error(self, syn_daily_df: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match="must be a date"):
            check_date_coverage(syn_daily_df, "event_date", None, "2021-01-05")

    def test_missing_column_raises_value_error(self, syn_daily_df: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match="not found in the DataFrame"):
            check_date_coverage(syn_daily_df, "date", "2021-01-01", "2021-01-05")


# ---------------------------------------------------------------------------
# 6. timestamp validity + microsecond helper
# ---------------------------------------------------------------------------


class TestMicrosToDatetime:
    """The microsecond unit trap must live in exactly one tested helper."""

    def test_converts_microseconds_to_utc(self) -> None:
        converted = micros_to_datetime(pd.Series([1_610_000_000_000_000]))
        assert str(converted.dtype) == "datetime64[us, UTC]"
        assert converted.iloc[0] == pd.Timestamp("2021-01-07T06:13:20Z")

    def test_missing_values_become_nat(self) -> None:
        converted = micros_to_datetime(pd.Series(pd.array([1_610_000_000_000_000, None], dtype="Int64")))
        assert converted.isna().tolist() == [False, True]

    def test_datetime_input_is_normalised_to_utc(self) -> None:
        converted = micros_to_datetime(pd.Series(pd.to_datetime(["2021-01-07T06:13:20Z"])))
        assert converted.dt.tz is not None
        assert converted.iloc[0] == pd.Timestamp("2021-01-07T06:13:20Z")

    def test_text_column_raises_type_error(self, syn_text_numbers_df: pd.DataFrame) -> None:
        with pytest.raises(TypeError, match="must have a numeric dtype"):
            micros_to_datetime(syn_text_numbers_df["event_timestamp"])

    def test_non_series_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="expected a pandas Series"):
            micros_to_datetime([1_610_000_000_000_000])  # type: ignore[arg-type]


class TestCheckTimestampValidity:
    """event_timestamp is microseconds; the wrong unit invalidates date filters."""

    def test_clean_window_passes(self, syn_timestamp_clean_df: pd.DataFrame) -> None:
        result = check_timestamp_validity(
            syn_timestamp_clean_df,
            "event_timestamp",
            JANUARY_2021_START_MICROS,
            FEBRUARY_2021_START_MICROS,
        )
        assert result.passed is True
        assert result.severity is Severity.INFORMATIONAL
        assert result.evidence["rows_null"] == 0
        assert result.evidence["unit"] == "microseconds since Unix epoch (GA4 native)"

    def test_implausible_and_null_timestamps_are_flagged(self, syn_timestamp_df: pd.DataFrame) -> None:
        result = check_timestamp_validity(
            syn_timestamp_df,
            "event_timestamp",
            JANUARY_2021_START_MICROS,
            FEBRUARY_2021_START_MICROS,
        )
        assert result.passed is False
        assert result.severity is Severity.HIGH
        assert result.evidence["rows_below_window"] == 1  # 1000 us == 1970, the unit trap
        assert result.evidence["rows_above_window"] == 1
        assert result.evidence["rows_null"] == 1
        assert result.metric_value == 3
        assert "MICROSECONDS" in result.message

    def test_dates_are_accepted_as_bounds(self, syn_timestamp_clean_df: pd.DataFrame) -> None:
        result = check_timestamp_validity(
            syn_timestamp_clean_df,
            "event_timestamp",
            date(2021, 1, 1),
            datetime(2021, 1, 31, 23, 59, 59, tzinfo=timezone.utc),
        )
        assert result.evidence["window_min_micros"] == JANUARY_2021_START_MICROS
        assert result.passed is True

    def test_datetime_column_is_supported(self) -> None:
        frame = pd.DataFrame({"event_timestamp": pd.to_datetime(["2021-01-05T00:00:00Z", None])})
        result = check_timestamp_validity(
            frame, "event_timestamp", "2021-01-01", "2021-01-31"
        )
        assert result.evidence["rows_null"] == 1
        assert result.evidence["rows_below_window"] == 0
        assert result.evidence["rows_above_window"] == 0

    def test_text_timestamp_column_raises_type_error(self, syn_text_numbers_df: pd.DataFrame) -> None:
        with pytest.raises(TypeError, match="must have a numeric dtype"):
            check_timestamp_validity(
                syn_text_numbers_df, "event_timestamp", JANUARY_2021_START_MICROS, FEBRUARY_2021_START_MICROS
            )

    def test_missing_bounds_raise_value_error(self, syn_timestamp_clean_df: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match="required"):
            check_timestamp_validity(syn_timestamp_clean_df, "event_timestamp")

    def test_reversed_bounds_raise_value_error(self, syn_timestamp_clean_df: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match="must not be after"):
            check_timestamp_validity(
                syn_timestamp_clean_df, "event_timestamp", FEBRUARY_2021_START_MICROS, JANUARY_2021_START_MICROS
            )

    def test_boolean_bound_raises_type_error(self, syn_timestamp_clean_df: pd.DataFrame) -> None:
        with pytest.raises(TypeError, match="got bool"):
            check_timestamp_validity(
                syn_timestamp_clean_df, "event_timestamp", True, FEBRUARY_2021_START_MICROS
            )

    def test_missing_column_raises_value_error(self, syn_timestamp_clean_df: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match="not found in the DataFrame"):
            check_timestamp_validity(
                syn_timestamp_clean_df, "event_ts", JANUARY_2021_START_MICROS, FEBRUARY_2021_START_MICROS
            )

    def test_empty_frame_is_handled(self) -> None:
        empty = pd.DataFrame({"event_timestamp": pd.Series([], dtype="int64")})
        result = check_timestamp_validity(
            empty, "event_timestamp", JANUARY_2021_START_MICROS, FEBRUARY_2021_START_MICROS
        )
        assert result.passed is True
        assert result.evidence["rows"] == 0


# ---------------------------------------------------------------------------
# 7. currency consistency
# ---------------------------------------------------------------------------


class TestCheckCurrencyConsistency:
    """Summing revenue across currencies adds amounts that are not comparable."""

    def test_single_currency_passes(self, syn_purchase_df: pd.DataFrame) -> None:
        result = check_currency_consistency(syn_purchase_df)
        assert result.passed is True
        assert result.metric_value == 1
        assert result.evidence["currencies"] == ["USD"]

    def test_currency_codes_are_normalised(self) -> None:
        frame = pd.DataFrame({"currency": [" usd ", "USD", "usd"]})
        result = check_currency_consistency(frame)
        assert result.passed is True
        assert result.evidence["distinct_currencies"] == 1

    def test_multiple_currencies_are_flagged(self, syn_multicurrency_df: pd.DataFrame) -> None:
        result = check_currency_consistency(syn_multicurrency_df)
        assert result.passed is False
        assert result.severity is Severity.HIGH
        assert result.evidence["currencies"] == ["EUR", "USD"]
        assert result.evidence["rows_missing_currency"] == 1
        assert result.evidence["rows_placeholder_currency"] == 1
        assert "non-comparable" in result.message

    def test_placeholders_are_not_counted_as_a_currency(self) -> None:
        frame = pd.DataFrame({"currency": ["USD", "(not set)", None]})
        result = check_currency_consistency(frame)
        assert result.passed is True
        assert result.evidence["currencies"] == ["USD"]
        assert result.evidence["rows_placeholder_currency"] == 1

    def test_no_usable_currency_reports_cannot_verify(self) -> None:
        frame = pd.DataFrame({"currency": [None, "(not set)"]})
        result = check_currency_consistency(frame)
        assert result.passed is True
        assert result.evidence["distinct_currencies"] == 0
        assert "could not be verified" in result.message

    def test_empty_frame_is_handled(self) -> None:
        result = check_currency_consistency(pd.DataFrame({"currency": pd.Series([], dtype="string")}))
        assert result.passed is True
        assert result.evidence["rows"] == 0

    def test_missing_column_raises_value_error(self, syn_purchase_df: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match="not found in the DataFrame"):
            check_currency_consistency(syn_purchase_df, currency_column="curr")

    def test_non_string_column_raises_type_error(self, syn_purchase_df: pd.DataFrame) -> None:
        with pytest.raises(TypeError, match="must be a string"):
            check_currency_consistency(syn_purchase_df, currency_column=3)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 8. revenue null rate
# ---------------------------------------------------------------------------


class TestCheckRevenueNullRate:
    """A NULL purchase_revenue is expected; an unquantified one is not."""

    def test_complete_columns_pass(self, syn_purchase_clean_df: pd.DataFrame) -> None:
        result = check_revenue_null_rate(
            syn_purchase_clean_df, "purchase_revenue", "purchase_revenue_in_usd"
        )
        assert result.passed is True
        assert result.metric_value == 0.0
        assert result.evidence["worst_null_rate"] == 0.0

    def test_partial_nulls_are_reported_with_ga4_explanation(
        self, syn_purchase_df: pd.DataFrame
    ) -> None:
        result = check_revenue_null_rate(
            syn_purchase_df, "purchase_revenue", "purchase_revenue_in_usd"
        )
        assert result.passed is False
        assert result.severity is Severity.MEDIUM
        assert result.metric_value == pytest.approx(0.4)
        assert result.evidence["per_column"]["purchase_revenue"]["null_rows"] == 2
        assert result.evidence["per_column"]["purchase_revenue_in_usd"]["null_rows"] == 0
        assert "EXPECTED GA4 behaviour" in result.message
        assert "currency" in result.message

    def test_fully_null_column_is_high_severity(self) -> None:
        frame = pd.DataFrame(
            {
                "purchase_revenue": pd.Series([None, None], dtype="float64"),
                "purchase_revenue_in_usd": pd.Series([1.0, 2.0], dtype="float64"),
            }
        )
        result = check_revenue_null_rate(frame, "purchase_revenue", "purchase_revenue_in_usd")
        assert result.passed is False
        assert result.severity is Severity.HIGH
        assert result.evidence["fully_null_columns"] == ["purchase_revenue"]
        assert "SUM over it returns 0" in result.message

    def test_tolerance_is_respected(self, syn_purchase_df: pd.DataFrame) -> None:
        result = check_revenue_null_rate(
            syn_purchase_df, "purchase_revenue", max_null_rate=0.5
        )
        assert result.passed is True
        assert result.severity is Severity.INFORMATIONAL

    def test_observed_sum_is_present_as_evidence(self, syn_purchase_df: pd.DataFrame) -> None:
        result = check_revenue_null_rate(syn_purchase_df, "purchase_revenue")
        assert result.evidence["per_column"]["purchase_revenue"]["observed_sum"] == pytest.approx(250.0)

    def test_no_columns_raises_value_error(self, syn_purchase_df: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match="at least one revenue column"):
            check_revenue_null_rate(syn_purchase_df)

    def test_text_revenue_column_raises_type_error(self, syn_text_numbers_df: pd.DataFrame) -> None:
        with pytest.raises(TypeError, match="must be numeric"):
            check_revenue_null_rate(syn_text_numbers_df, "purchase_revenue")

    def test_missing_column_raises_value_error(self, syn_purchase_df: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match="not found in the DataFrame"):
            check_revenue_null_rate(syn_purchase_df, "revenue")

    def test_bad_tolerance_raises(self, syn_purchase_df: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match="between 0.0 and 1.0"):
            check_revenue_null_rate(syn_purchase_df, "purchase_revenue", max_null_rate=2)

    def test_empty_frame_is_handled(self) -> None:
        empty = pd.DataFrame({"purchase_revenue": pd.Series([], dtype="float64")})
        result = check_revenue_null_rate(empty, "purchase_revenue")
        assert result.passed is True
        assert result.evidence["rows"] == 0


# ---------------------------------------------------------------------------
# 9. session id reuse
# ---------------------------------------------------------------------------


class TestCheckSessionIdReuse:
    """ga_session_id is unique per user, never globally: the composite key matters."""

    def test_reuse_is_observed_and_matches_expectation(self, syn_session_df: pd.DataFrame) -> None:
        result = check_session_id_reuse(syn_session_df)
        assert result.passed is True
        assert result.severity is Severity.INFORMATIONAL
        assert result.evidence["reused_session_ids"] == 1
        assert result.evidence["max_users_per_session_id"] == 2
        assert result.evidence["sample_reused_session_ids"] == ["1001"]
        assert result.evidence["rows_excluded_missing_ids"] == 1
        assert "not corruption" in result.message

    def test_pass_semantics_are_stated_in_the_result(self, syn_session_df: pd.DataFrame) -> None:
        result = check_session_id_reuse(syn_session_df)
        assert result.evidence["pass_means"] == "observed reuse matches the documented GA4 expectation"
        assert "PASS here means" in result.message

    def test_pipeline_assuming_global_uniqueness_is_alarmed(self, syn_session_df: pd.DataFrame) -> None:
        result = check_session_id_reuse(syn_session_df, expect_reuse=False)
        assert result.passed is False
        assert result.severity is Severity.HIGH
        assert "uniqueness assumption is false" in result.message
        assert result.threshold == 0

    def test_no_reuse_when_reuse_expected_is_medium(self, syn_clean_session_df: pd.DataFrame) -> None:
        result = check_session_id_reuse(syn_clean_session_df)
        assert result.passed is False
        assert result.severity is Severity.MEDIUM
        assert result.evidence["reused_session_ids"] == 0
        assert "could not be demonstrated" in result.message

    def test_no_reuse_when_uniqueness_assumed_passes(self, syn_clean_session_df: pd.DataFrame) -> None:
        result = check_session_id_reuse(syn_clean_session_df, expect_reuse=False)
        assert result.passed is True
        assert result.severity is Severity.INFORMATIONAL

    def test_nullable_session_ids_are_supported(self) -> None:
        frame = pd.DataFrame(
            {
                "user_pseudo_id": ["u1", "u2", "u1"],
                "ga_session_id": pd.array([1001, 1001, None], dtype="Int64"),
            }
        )
        result = check_session_id_reuse(frame)
        assert result.evidence["reused_session_ids"] == 1
        assert result.evidence["rows_excluded_missing_ids"] == 1

    def test_rows_without_ids_report_medium_severity(self, syn_missing_key_df: pd.DataFrame) -> None:
        result = check_session_id_reuse(syn_missing_key_df)
        assert result.passed is False
        assert result.severity is Severity.MEDIUM
        assert result.evidence["rows_excluded_missing_ids"] == 3

    def test_missing_column_raises_value_error(self, syn_session_df: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match="not found in the DataFrame"):
            check_session_id_reuse(syn_session_df, session_id_column="session_id")

    def test_non_bool_expectation_raises_type_error(self, syn_session_df: pd.DataFrame) -> None:
        with pytest.raises(TypeError, match="expect_reuse must be a bool"):
            check_session_id_reuse(syn_session_df, expect_reuse="yes")  # type: ignore[arg-type]

    def test_empty_frame_is_handled(self) -> None:
        empty = pd.DataFrame(
            {"user_pseudo_id": pd.Series([], dtype="string"), "ga_session_id": pd.Series([], dtype="int64")}
        )
        result = check_session_id_reuse(empty)
        assert result.passed is True
        assert result.evidence["rows"] == 0


# ---------------------------------------------------------------------------
# 10. share bounds
# ---------------------------------------------------------------------------


class TestCheckShareBounds:
    """A rate outside [0, 1] means the numerator and denominator disagree."""

    def test_values_in_range_pass(self, syn_funnel_monotonic_df: pd.DataFrame) -> None:
        frame = pd.DataFrame({"conversion_rate": [0.0, 0.5, 1.0]})
        result = check_share_bounds(frame, "conversion_rate")
        assert result.passed is True
        assert result.metric_value == 0
        assert result.evidence["observed_min"] == 0.0
        assert result.evidence["observed_max"] == 1.0
        assert not syn_funnel_monotonic_df.empty

    def test_out_of_range_values_are_flagged(self, syn_share_df: pd.DataFrame) -> None:
        result = check_share_bounds(syn_share_df, "conversion_rate")
        assert result.passed is False
        assert result.severity is Severity.HIGH
        assert result.metric_value == 2
        assert result.evidence["null_values"] == 1
        assert result.evidence["observed_min"] == pytest.approx(-0.1)
        assert result.evidence["observed_max"] == pytest.approx(1.5)
        assert "computed over different populations" in result.message

    def test_custom_bounds_are_applied(self) -> None:
        frame = pd.DataFrame({"conversion_rate": [50.0, 150.0]})
        assert check_share_bounds(frame, "conversion_rate", high=100.0).passed is False
        assert check_share_bounds(frame, "conversion_rate", high=200.0).passed is True

    def test_nulls_do_not_fail_the_check(self) -> None:
        frame = pd.DataFrame({"conversion_rate": pd.Series([None, None], dtype="float64")})
        result = check_share_bounds(frame, "conversion_rate")
        assert result.passed is True
        assert result.evidence["values_checked"] == 0
        assert result.evidence["null_values"] == 2
        assert result.evidence["observed_min"] is None

    def test_reversed_bounds_raise_value_error(self) -> None:
        frame = pd.DataFrame({"conversion_rate": [0.5]})
        with pytest.raises(ValueError, match="must not be greater than"):
            check_share_bounds(frame, "conversion_rate", low=1.0, high=0.0)

    def test_non_numeric_bounds_raise_type_error(self) -> None:
        frame = pd.DataFrame({"conversion_rate": [0.5]})
        with pytest.raises(TypeError, match="must be numbers"):
            check_share_bounds(frame, "conversion_rate", low="0")  # type: ignore[arg-type]

    def test_text_column_raises_type_error(self, syn_text_numbers_df: pd.DataFrame) -> None:
        with pytest.raises(TypeError, match="must be numeric"):
            check_share_bounds(syn_text_numbers_df, "conversion_rate")

    def test_missing_column_raises_value_error(self, syn_share_df: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match="not found in the DataFrame"):
            check_share_bounds(syn_share_df, "rate")

    def test_empty_frame_is_handled(self) -> None:
        result = check_share_bounds(pd.DataFrame({"conversion_rate": pd.Series([], dtype="float64")}), "conversion_rate")
        assert result.passed is True
        assert result.evidence["rows"] == 0


# ---------------------------------------------------------------------------
# All checks together + optional human-provided aggregates
# ---------------------------------------------------------------------------


class TestChecksOnMultipleAggregates:
    """Smoke coverage: every check must return a CheckResult on a clean frame."""

    def test_every_check_returns_a_json_serialisable_result(
        self, syn_clean_session_df: pd.DataFrame
    ) -> None:
        frame = syn_clean_session_df
        results = [
            check_no_null_identifiers(frame),
            check_duplicate_composite_key(frame, ["user_pseudo_id", "ga_session_id"]),
            check_session_id_reuse(frame, expect_reuse=False),
            check_currency_consistency(frame),
            check_date_coverage(frame, "session_date", "2021-01-01", "2021-01-04"),
            check_share_bounds(frame, "conversion_rate"),
        ]
        for result in results:
            assert isinstance(result, CheckResult)
            assert result.message
            json.dumps(result.to_dict())

    def test_real_aggregate_fixtures_load_or_skip(
        self, real_aggregate_fixtures: dict[str, pd.DataFrame]
    ) -> None:
        """Human-added CSVs in ``tests/fixtures/`` must at least be valid aggregates.

        Skips on a clean checkout: the repository ships **no** real data, only
        synthetic fixtures built in ``conftest.py``.
        """
        if not real_aggregate_fixtures:
            pytest.skip(
                "tests/fixtures/ contains no CSV aggregate (expected on a clean checkout; "
                "see tests/fixtures/README.md)"
            )
        for name, frame in real_aggregate_fixtures.items():
            assert not frame.empty, f"fixture {name!r} is an empty CSV"
            assert frame.shape[1] >= 2, f"fixture {name!r} has too few columns to be an aggregate"
