"""Formatter to process mypy output and yield GitHub annotations."""

import json
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel

from github_checks.formatters.utils import filter_for_checksignore, get_conclusion
from github_checks.models import (
    AnnotationLevel,
    CheckAnnotation,
    CheckRunConclusion,
    CheckRunOutput,
)

MYPY_ISSUE_CODE_URL_BASE = "https://mypy.rtfd.io/en/stable/_refs.html#code-"
MYPY_DETAILS_HINT_TEMPLATE = (
    "See " + MYPY_ISSUE_CODE_URL_BASE + "{code} for more information."
)


class _MyPySeverity(StrEnum):
    """Enum for mypy severity levels."""

    ERROR = "error"
    NOTE = "note"


class _MyPyJSONError(BaseModel):
    """Model for a single mypy error in JSON output."""

    file: str
    line: int
    column: int  # note: mypy only gives start positions
    message: str
    hint: str | None  # set inconsistently by --show-error-code-links, we don't use this
    code: str
    severity: _MyPySeverity


def format_mypy_check_run_output(
    json_output_fp: Path,
    local_repo_base: Path,
    ignore_globs: list[str] | None = None,
    *,
    ignore_verdict_only: bool = False,
) -> tuple[CheckRunOutput, CheckRunConclusion]:
    """Generate high level results, to be shown on the "Checks" tab."""
    with json_output_fp.open("r", encoding="utf-8") as json_file:
        json_content = [
            json.loads(line) for line in json_file.readlines() if line.strip()
        ]  # mypy outputs one JSON object per line

    annotations: list[CheckAnnotation] = []
    issue_codes = set()
    for error_dict in json_content:
        mypy_err: _MyPyJSONError = _MyPyJSONError.model_validate(error_dict)
        message = (
            mypy_err.message
            + "\n\n"
            + MYPY_DETAILS_HINT_TEMPLATE.format(
                code=mypy_err.code,
            )
        )
        annotation_level = (
            AnnotationLevel.NOTICE
            if mypy_err.severity == _MyPySeverity.NOTE
            else AnnotationLevel.WARNING
        )
        annotations.append(
            CheckAnnotation(
                path=mypy_err.file,
                start_line=mypy_err.line,
                end_line=mypy_err.line,
                start_column=mypy_err.column,
                end_column=mypy_err.column,
                annotation_level=annotation_level,
                message=message,
                title=f"[{mypy_err.code}]",
            ),
        )
        issue_codes.add(mypy_err.code)

    # Filter out ignored files from the verdict / annotations (depending on settings)
    if ignore_globs:
        filtered_annotations: list[CheckAnnotation] = list(
            filter_for_checksignore(
                annotations,
                ignore_globs,
                local_repo_base,
            ),
        )
        conclusion = get_conclusion(filtered_annotations)
        if not ignore_verdict_only:
            annotations = filtered_annotations
    else:
        conclusion = get_conclusion(annotations)

    if annotations:
        issues_text = "\n".join(
            f"> **[[{code}]({MYPY_ISSUE_CODE_URL_BASE + code})]**"
            for code in issue_codes
        )
        summary = (
            f"Mypy found the following issues:\n{issues_text}\n\n"
            "Click the error codes to check out why mypy thinks these are bad, or go "
            "to the source files to check out the annotations on the offending code."
        )
        if conclusion == CheckRunConclusion.ACTION_REQUIRED:
            title = f"Mypy found {len(issue_codes)} distinct issues."
        else:
            title = "Mypy only found issues in ignored files."

    else:
        title = "Mypy found no issues."
        summary = "Nice work!"

    return (
        CheckRunOutput(
            title=title,
            summary=summary,
            annotations=annotations,
        ),
        conclusion,
    )
