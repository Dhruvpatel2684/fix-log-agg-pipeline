"""
Type Flow Analysis Entry Point
================================

Orchestrates the complete type checking analysis workflow:
    1. Discovers program specification files
    2. Parses each program spec into typed AST
    3. Validates all assignments using the subtype checker
    4. Generates structured JSON reports

Usage:
    python3 -m runtime.run_analysis

Configuration:
    - Input directory: /app/runtime/data/ (JSON program specs)
    - Output directory: /app/runtime/data/ (analysis reports)
"""

from __future__ import annotations

import glob
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

from .parser import ProgramSpecParser
from .validator import AssignmentValidator, ProgramValidationResult
from .reporter import ReportConfig, ReportGenerator


# ============================================================================
# Configuration
# ============================================================================

DEFAULT_DATA_DIR = "/app/runtime/data"
DEFAULT_PROGRAM_PATTERN = "program_*.json"
DEFAULT_REPORT_FILE = "analysis_report.json"


# ============================================================================
# Analysis Runner
# ============================================================================

class AnalysisRunner:
    """
    Coordinates the type flow analysis process from start to finish.
    """

    def __init__(
        self,
        data_dir: str = DEFAULT_DATA_DIR,
        report_file: str = DEFAULT_REPORT_FILE,
    ) -> None:
        self._data_dir = data_dir
        self._report_file = report_file
        self._parser = ProgramSpecParser()
        self._validator = AssignmentValidator()
        self._start_time: float = 0.0

    def run(self) -> Dict[str, Any]:
        """
        Execute the complete analysis workflow.

        Returns:
            Summary dictionary with analysis results.
        """
        self._start_time = time.time()

        print(f"[TypeFlow] Starting analysis...")
        print(f"[TypeFlow] Data directory: {self._data_dir}")

        # Step 1: Discover program files
        program_files = self._discover_programs()
        print(f"[TypeFlow] Found {len(program_files)} program specifications")

        if not program_files:
            print("[TypeFlow] No program files found. Exiting.")
            return {"status": "no_programs", "programs": 0}

        # Step 2: Parse program specs
        print("[TypeFlow] Parsing program specifications...")
        specs = self._parser.parse_multiple(program_files)
        parse_stats = self._parser.get_stats()
        print(f"[TypeFlow] Parsed {parse_stats['parsed']} programs, {parse_stats['errors']} errors")

        # Step 3: Validate assignments
        print("[TypeFlow] Validating type assignments...")
        validation_results = self._validator.validate_multiple(specs)
        val_stats = self._validator.get_statistics()
        print(f"[TypeFlow] Validated {val_stats['total_validated']} assignments")
        print(f"[TypeFlow]   Valid: {val_stats['total_valid']}")
        print(f"[TypeFlow]   Invalid: {val_stats['total_invalid']}")

        # Step 4: Generate report
        print("[TypeFlow] Generating analysis report...")
        report_config = ReportConfig(
            output_directory=self._data_dir,
            report_filename=self._report_file,
            include_explanations=True,
            include_timing=True,
            per_program_files=True,
        )
        reporter = ReportGenerator(report_config)
        report_path = reporter.write_report(validation_results)
        print(f"[TypeFlow] Report written to: {report_path}")

        # Summary
        elapsed = time.time() - self._start_time
        print(f"[TypeFlow] Analysis complete in {elapsed:.2f}s")

        return {
            "status": "complete",
            "programs": len(program_files),
            "total_assignments": val_stats["total_validated"],
            "valid": val_stats["total_valid"],
            "invalid": val_stats["total_invalid"],
            "report_path": report_path,
            "elapsed_seconds": round(elapsed, 3),
        }

    def _discover_programs(self) -> List[str]:
        """Find all program specification JSON files."""
        pattern = os.path.join(self._data_dir, DEFAULT_PROGRAM_PATTERN)
        files = sorted(glob.glob(pattern))
        return files


# ============================================================================
# Main Entry Point
# ============================================================================

def main() -> None:
    """Main entry point for the analysis runner."""
    data_dir = os.environ.get("TYPEFLOW_DATA_DIR", DEFAULT_DATA_DIR)
    report_file = os.environ.get("TYPEFLOW_REPORT_FILE", DEFAULT_REPORT_FILE)

    runner = AnalysisRunner(data_dir=data_dir, report_file=report_file)

    try:
        result = runner.run()
        if result["status"] == "complete":
            print(f"\n[TypeFlow] SUCCESS: Analyzed {result['programs']} programs")
            sys.exit(0)
        else:
            print(f"\n[TypeFlow] WARNING: {result['status']}")
            sys.exit(0)
    except Exception as e:
        print(f"\n[TypeFlow] ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
