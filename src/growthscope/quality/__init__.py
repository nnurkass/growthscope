"""Data-quality validation for GrowthScope aggregates.

This sub-package validates the **aggregated pandas DataFrames produced by the
SQL exploration queries** in ``sql/exploration/``. It deliberately does not
touch the raw GA4 export: transferring millions of nested event rows to count
NULLs would be expensive and would duplicate what SQL does better. Instead, every
check takes a small, already-fetched aggregate and answers one narrow question
about it.

All checks are pure functions: no I/O, no network, no printing, deterministic
output, no mutation of the input frame.

Typical use::

    from growthscope.quality import check_duplicate_composite_key

    result = check_duplicate_composite_key(sessions_df, ["user_pseudo_id", "ga_session_id"])
    if not result.passed:
        print(result.severity.value, result.message, result.evidence)
"""

from .checks import (
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
from .models import CheckResult, Severity

__all__ = [
    "CheckResult",
    "Severity",
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
