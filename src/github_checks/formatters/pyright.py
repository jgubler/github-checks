"""
Pyright JSON Formatter Module.

This module provides functionality to parse the JSON output of Pyright
and convert it into annotations and summaries suitable for GitHub Checks.
It includes models for diagnostics, severity levels, and report summaries.
"""

import json
from collections import defaultdict
from enum import StrEnum, auto
from pathlib import Path

from pydantic import BaseModel

from github_checks.formatters.utils import filter_for_checksignore, get_conclusion
from github_checks.models import (
    AnnotationLevel,
    CheckAnnotation,
    CheckRunConclusion,
    CheckRunOutput,
)


class DiagnosticPosition(BaseModel):
    """Represents a position in the source code with line and character numbers.

    Attributes:
        line (int): The line number (0-based).
        character (int): The character position within the line (0-based).
    """

    line: int
    character: int


class DiagnosticRange(BaseModel):
    """Represents a range in the source code with start and end positions.

    Attributes:
        start (DiagnosticPosition): The starting position of the range.
        end (DiagnosticPosition): The ending position of the range.
    """

    start: DiagnosticPosition
    end: DiagnosticPosition


class PyrightSeverity(StrEnum):
    """Enumeration of severity levels used by Pyright diagnostics.

    This class defines the severity levels for issues detected by Pyright,
    such as errors, warnings, and informational messages.
    """

    ERROR = auto()
    WARNING = auto()
    INFORMATION = auto()

    @classmethod
    def to_annotation_level(cls, severity: "PyrightSeverity") -> AnnotationLevel:
        """Convert Pyright severity to GitHub Check AnnotationLevel.

        Args:
            severity (PyrightSeverity): The severity level from Pyright.

        Returns:
            AnnotationLevel: The corresponding GitHub Check AnnotationLevel.
        """
        if severity == cls.ERROR:
            return AnnotationLevel.FAILURE
        if severity == cls.WARNING:
            return AnnotationLevel.WARNING
        return AnnotationLevel.NOTICE


class PyrightDiagnostic(BaseModel):
    """Represents a diagnostic message from Pyright.

    Attributes:
        file (str): The file where the diagnostic was reported.
        severity (PyrightSeverity): The severity level of the diagnostic.
        message (str): The diagnostic message.
        rule (Optional[str]): The rule or code associated with the diagnostic, if any.
        range (DiagnosticRange): The code range in which the issue was detected.
    """

    file: str
    severity: PyrightSeverity = PyrightSeverity.INFORMATION
    message: str
    rule: str | None = None
    range: DiagnosticRange


class PyrightSummary(BaseModel):
    """Summary of the Pyright analysis results.

    Attributes:
        filesAnalyzed (int): The number of files analyzed by Pyright.
        errorCount (int): The total number of errors found.
        warningCount (int): The total number of warnings found.
        informationCount (int): The total number of informational messages found.
        timeInSec (float): The time taken for the analysis in seconds.
    """

    filesAnalyzed: int  # noqa: N815
    errorCount: int  # noqa: N815
    warningCount: int  # noqa: N815
    informationCount: int  # noqa: N815
    timeInSec: float  # noqa: N815


class PyrightReport(BaseModel):
    """Represents the full Pyright analysis report.

    Attributes:
        version (str): The version of Pyright used for the analysis.
        time (str): The timestamp of when the analysis was performed.
        generalDiagnostics (list[PyrightDiagnostic]): A list of diagnostic messages.
        summary (PyrightSummary): A summary of the analysis results.
    """

    version: str
    time: str
    generalDiagnostics: list[PyrightDiagnostic]  # noqa: N815
    summary: PyrightSummary


def format_pyright_check_run_output(
    json_output_fp: Path,
    local_repo_base: Path,
    ignored_globs: list[str] | None = None,
    *,
    ignore_verdict_only: bool = False,
) -> tuple[CheckRunOutput, CheckRunConclusion]:
    """Generate high level results, to be shown on the "Checks" tab."""
    with json_output_fp.open("r", encoding="utf-8") as json_file:
        first_line = json_file.readline()
        # for some reason, pyright stdout sometimes starts with a line like this:
        # {'x86': False, 'risc': False, 'lts': False}  # noqa: ERA001
        # I suspect it's a side effect of running node, but don't know for sure.
        if first_line.startswith("{'x86'"):
            # it's here, skip it, as it's neither relevant to the report nor valid JSON
            pass
        else:
            # weird line is not present, rewind to start
            json_file.seek(0)
        json_content = json.load(json_file)
    report = PyrightReport.model_validate(json_content)

    annotations: list[CheckAnnotation] = []
    rule_counts: defaultdict[str, int] = defaultdict(int)  # auto-initialized to 0

    for diag in report.generalDiagnostics:
        annotations.append(get_annotation(diag, local_repo_base))
        if diag.rule:
            rule_counts[diag.rule] += 1

    # Filter out ignored files from the verdict / annotations (depending on settings)
    if ignored_globs:
        filtered_annotations: list[CheckAnnotation] = list(
            filter_for_checksignore(
                annotations,
                ignored_globs,
                local_repo_base,
            ),
        )
        conclusion = get_conclusion(filtered_annotations)
        if not ignore_verdict_only:
            annotations = filtered_annotations
    else:
        conclusion = get_conclusion(annotations)

    title, summary = get_summary_and_title(conclusion, report.summary, rule_counts)

    return (
        CheckRunOutput(
            title=title,
            summary=summary,
            annotations=annotations,
        ),
        conclusion,
    )


def get_summary_and_title(
    conclusion: CheckRunConclusion,
    report_summary: PyrightSummary,
    rule_counts: dict[str, int],
) -> tuple[str, str]:
    """Generate a summary and title for the Pyright check run.

    Args:
        conclusion (CheckRunConclusion): The overall conclusion of the check run.
        report_summary (PyrightSummary): The summary of the Pyright analysis results.
        rule_counts (dict[str, int]): A dict mapping rules to their occurrence counts.

    Returns:
        tuple[str, str]: A tuple containing the title and summary for the check run.
    """
    title: str
    num_issues: int = (
        report_summary.errorCount
        + report_summary.warningCount
        + report_summary.informationCount
    )
    if conclusion == CheckRunConclusion.ACTION_REQUIRED:
        title = f"Pyright found {num_issues} total issue(s), some require resolution."
    elif num_issues > 0:
        title = f"Pyright found no issues needing resolution, but {num_issues} notices."
    else:
        title = "Pyright found no issues."

    if num_issues == 0:
        summary = "Nice work!"
    else:
        rules_summary = "\n".join(
            f"- `{rule}` ({count})" for rule, count in rule_counts.items()
        )
        errnum = report_summary.errorCount
        warnnum = report_summary.warningCount
        info_num = report_summary.informationCount
        summary = "\n".join(
            (
                f"{errnum} Errors, {warnnum} Warnings, {info_num} Informational",
                "Rules triggered:",
                rules_summary,
            ),
        )
    return title, summary


def get_annotation(diag: PyrightDiagnostic, local_repo_base: Path) -> CheckAnnotation:
    """Convert a Pyright diagnostic object into a GitHub Check Annotation.

    This function processes the diagnostic information provided by Pyright,
    including the range of the issue, severity, and message, and formats it
    into a GitHub Check Annotation. The range fields from Pyright, which are
    zero-based, are converted to one-based line and column numbers to match
    GitHub's requirements.

    Args:
        diag (PyrightDiagnostic): The diagnostic object containing details
            about the issue, such as its location, severity, and message.

    Returns:
        CheckAnnotation: A formatted annotation object containing the file path,
            issue range, severity level, and message for GitHub Checks.
    """
    rng = diag.range
    start_line = rng.start.line + 1
    end_line = rng.end.line + 1
    start_column = rng.start.character + 1
    end_column = rng.end.character + 1

    annotation_level = PyrightSeverity.to_annotation_level(diag.severity)

    return CheckAnnotation(
        path=str(Path(diag.file).relative_to(local_repo_base)),
        start_line=start_line,
        end_line=end_line,
        start_column=start_column,
        end_column=end_column,
        annotation_level=annotation_level,
        title=f"[{diag.rule}]" if diag.rule else "Uncategorized Pyright Issue",
        message=diag.message,
    )
