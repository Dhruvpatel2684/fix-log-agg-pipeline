"""
Structured Report Generator
============================

Generates JSON output reports from validation results. Provides
per-assignment validation details, summary statistics, type error
descriptions, and overall analysis metrics.

Output Format:
    {
        "analysis_version": "1.4.2",
        "programs": [...],
        "summary": {...},
        "metadata": {...}
    }
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .validator import AssignmentValidationResult, ProgramValidationResult


# ============================================================================
# Report Configuration
# ============================================================================

@dataclass
class ReportConfig:
    """Configuration for report generation."""

    output_directory: str = "/app/runtime/data"
    include_explanations: bool = True
    include_timing: bool = True
    include_metadata: bool = True
    indent: int = 2
    max_explanation_length: int = 500
    summary_only: bool = False
    per_program_files: bool = True
    combined_report: bool = True
    report_filename: str = "analysis_report.json"


# ============================================================================
# Report Data Structures
# ============================================================================

@dataclass
class AssignmentReport:
    """Report entry for a single assignment."""

    id: str
    target: str
    target_type: str
    source: str
    source_type: str
    valid: bool
    confidence: float
    category: str
    explanation: str = ""
    check_time_ms: float = 0.0

    def to_dict(self, config: ReportConfig) -> Dict[str, Any]:
        """Convert to output dictionary."""
        result: Dict[str, Any] = {
            "id": self.id,
            "target": self.target,
            "target_type": self.target_type,
            "source": self.source,
            "source_type": self.source_type,
            "valid": self.valid,
            "confidence": self.confidence,
            "category": self.category,
        }
        if config.include_explanations:
            explanation = self.explanation
            if len(explanation) > config.max_explanation_length:
                explanation = explanation[:config.max_explanation_length] + "..."
            result["explanation"] = explanation
        if config.include_timing:
            result["check_time_ms"] = round(self.check_time_ms, 4)
        return result


@dataclass
class ProgramReport:
    """Report for a single program."""

    name: str
    total_assignments: int
    valid_count: int
    invalid_count: int
    validity_ratio: float
    assignments: List[AssignmentReport] = field(default_factory=list)
    validation_time_ms: float = 0.0
    warnings: List[str] = field(default_factory=list)

    def to_dict(self, config: ReportConfig) -> Dict[str, Any]:
        """Convert to output dictionary."""
        result: Dict[str, Any] = {
            "name": self.name,
            "total_assignments": self.total_assignments,
            "valid_count": self.valid_count,
            "invalid_count": self.invalid_count,
            "validity_ratio": round(self.validity_ratio, 4),
        }
        if not config.summary_only:
            result["assignments"] = [a.to_dict(config) for a in self.assignments]
        if config.include_timing:
            result["validation_time_ms"] = round(self.validation_time_ms, 3)
        if self.warnings:
            result["warnings"] = self.warnings
        return result


@dataclass
class SummaryReport:
    """Overall summary across all programs."""

    total_programs: int
    total_assignments: int
    total_valid: int
    total_invalid: int
    overall_validity_ratio: float
    categories_breakdown: Dict[str, Dict[str, int]] = field(default_factory=dict)
    total_time_ms: float = 0.0

    def to_dict(self, config: ReportConfig) -> Dict[str, Any]:
        """Convert to output dictionary."""
        result: Dict[str, Any] = {
            "total_programs": self.total_programs,
            "total_assignments": self.total_assignments,
            "total_valid": self.total_valid,
            "total_invalid": self.total_invalid,
            "overall_validity_ratio": round(self.overall_validity_ratio, 4),
        }
        if self.categories_breakdown:
            result["categories"] = self.categories_breakdown
        if config.include_timing:
            result["total_time_ms"] = round(self.total_time_ms, 3)
        return result


# ============================================================================
# Report Generator
# ============================================================================

class ReportGenerator:
    """
    Generates structured JSON reports from validation results.
    """

    def __init__(self, config: Optional[ReportConfig] = None) -> None:
        self._config = config or ReportConfig()
        self._generation_start: float = 0.0

    def generate_report(
        self, validation_results: List[ProgramValidationResult]
    ) -> Dict[str, Any]:
        """
        Generate the complete analysis report from validation results.

        Returns:
            Dictionary ready for JSON serialization.
        """
        self._generation_start = time.time()

        program_reports = [
            self._build_program_report(vr) for vr in validation_results
        ]
        summary = self._build_summary(program_reports)

        report: Dict[str, Any] = {
            "analysis_version": "1.4.2",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "programs": [pr.to_dict(self._config) for pr in program_reports],
            "summary": summary.to_dict(self._config),
        }

        if self._config.include_metadata:
            report["metadata"] = self._build_metadata(validation_results)

        return report

    def write_report(
        self, validation_results: List[ProgramValidationResult]
    ) -> str:
        """
        Generate and write the report to the configured output file.

        Returns:
            Path to the written report file.
        """
        report = self.generate_report(validation_results)

        output_dir = Path(self._config.output_directory)
        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = output_dir / self._config.report_filename
        with open(output_path, "w") as f:
            json.dump(report, f, indent=self._config.indent)

        # Write per-program files if configured
        if self._config.per_program_files:
            for vr in validation_results:
                program_report = self._build_program_report(vr)
                program_path = output_dir / f"report_{vr.program_name}.json"
                with open(program_path, "w") as f:
                    json.dump(
                        program_report.to_dict(self._config),
                        f,
                        indent=self._config.indent,
                    )

        return str(output_path)

    def _build_program_report(self, vr: ProgramValidationResult) -> ProgramReport:
        """Build a ProgramReport from a ProgramValidationResult."""
        assignment_reports = [
            AssignmentReport(
                id=ar.assignment_id,
                target=ar.target_variable,
                target_type=ar.target_type_display,
                source=ar.source_expression,
                source_type=ar.source_type_display,
                valid=ar.is_valid,
                confidence=ar.confidence,
                category=ar.category,
                explanation=ar.explanation,
                check_time_ms=ar.check_time_ms,
            )
            for ar in vr.assignments
        ]

        return ProgramReport(
            name=vr.program_name,
            total_assignments=vr.total_assignments,
            valid_count=vr.valid_count,
            invalid_count=vr.invalid_count,
            validity_ratio=vr.validity_ratio,
            assignments=assignment_reports,
            validation_time_ms=vr.validation_time_ms,
            warnings=vr.warnings,
        )

    def _build_summary(self, program_reports: List[ProgramReport]) -> SummaryReport:
        """Build overall summary from program reports."""
        total_programs = len(program_reports)
        total_assignments = sum(pr.total_assignments for pr in program_reports)
        total_valid = sum(pr.valid_count for pr in program_reports)
        total_invalid = sum(pr.invalid_count for pr in program_reports)

        overall_ratio = total_valid / total_assignments if total_assignments > 0 else 0.0

        # Build category breakdown
        categories: Dict[str, Dict[str, int]] = {}
        for pr in program_reports:
            for ar in pr.assignments:
                if ar.category not in categories:
                    categories[ar.category] = {"valid": 0, "invalid": 0}
                if ar.valid:
                    categories[ar.category]["valid"] += 1
                else:
                    categories[ar.category]["invalid"] += 1

        total_time = sum(pr.validation_time_ms for pr in program_reports)

        return SummaryReport(
            total_programs=total_programs,
            total_assignments=total_assignments,
            total_valid=total_valid,
            total_invalid=total_invalid,
            overall_validity_ratio=overall_ratio,
            categories_breakdown=categories,
            total_time_ms=total_time,
        )

    def _build_metadata(
        self, validation_results: List[ProgramValidationResult]
    ) -> Dict[str, Any]:
        """Build metadata section of the report."""
        return {
            "checker_version": "1.4.2",
            "output_directory": self._config.output_directory,
            "include_explanations": self._config.include_explanations,
            "programs_analyzed": len(validation_results),
            "generation_time_ms": round(
                (time.time() - self._generation_start) * 1000, 3
            ),
        }
