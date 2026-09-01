"""UI-facing validation result model.

A thin, dependency-free mirror of :class:`solafune_change.types.ValidationReport`
so the dock widget module can be imported (and unit-tested) without the core
engine's dependencies installed. :func:`from_core_report` does the one-way
conversion when a real report is available.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class UiValidationIssue:
    severity: str
    code: str
    message: str


@dataclass
class UiValidationReport:
    status: str = "not_run"  # not_run | valid | valid_with_warnings | invalid
    issues: list[UiValidationIssue] = field(default_factory=list)
    band_metadata: list[dict] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return self.status in ("valid", "valid_with_warnings")


def from_core_report(report) -> UiValidationReport:
    return UiValidationReport(
        status=report.status,
        issues=[UiValidationIssue(i.severity, i.code, i.message) for i in report.issues],
        band_metadata=list(report.band_metadata),
    )
