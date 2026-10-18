"""Result types for the GrowthScope data-quality checks.

The types here are deliberately tiny: a severity scale and one immutable result
object. Every check in :mod:`growthscope.quality.checks` returns a
:class:`CheckResult`, which keeps results renderable (a dashboard, a Markdown
audit table or a pytest assertion all read the same object) and testable.

Design notes
------------
* ``Severity.CRITICAL`` is part of the documented scale used by
  ``docs/data_quality_audit.md`` but is never emitted by the automated checks:
  a Critical condition in this project means "the dataset itself cannot be
  evaluated at all" (for example: no BigQuery access, dataset removed), which no
  in-process check can observe from a DataFrame.
* ``evidence`` is a plain mapping so it can be dumped straight into JSON.
  Because it holds a ``dict``, ``CheckResult`` is immutable-by-convention rather
  than hashable: treat the ``evidence`` payload as read-only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class Severity(str, Enum):
    """How much attention a check result deserves.

    Values are lower-case strings so they serialise cleanly into JSON/Markdown.
    """

    INFORMATIONAL = "informational"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class CheckResult:
    """Outcome of a single data-quality check.

    Attributes
    ----------
    name:
        Stable identifier of the check, e.g. ``"duplicate_composite_key"``.
    passed:
        ``True`` when the observation is within the configured tolerance.
        ``passed`` is always about the *threshold*, never about "the dataset is
        good": several checks in this library intentionally fail on expected GA4
        behaviour (see ``check_session_id_reuse``) and say so in ``message``.
    severity:
        Attention level for a human reader. Assigned independently from
        ``passed`` so that an expected-but-important fact can be reported
        Informational while a real defect is reported High.
    metric_value:
        The observed value the decision was made on (usually a share or a row
        count). ``None`` when the check had nothing to measure.
    threshold:
        The tolerance the observation was compared against, for rendering.
    message:
        Human-readable explanation, including the GA4 semantics that make the
        result interpretable. Never a stack trace, never chain-of-thought.
    evidence:
        Machine-readable supporting detail (counts, samples, affected keys).
    """

    name: str
    passed: bool
    severity: Severity
    metric_value: float | int | None
    threshold: float | int | None
    message: str
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable view of the result."""
        return {
            "name": self.name,
            "passed": bool(self.passed),
            "severity": self.severity.value,
            "metric_value": self.metric_value,
            "threshold": self.threshold,
            "message": self.message,
            "evidence": dict(self.evidence),
        }
