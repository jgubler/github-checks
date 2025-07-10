"""Formatter to process ruff output and yield GitHub annotations."""

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from github_checks.models import (
    AnnotationLevel,
    CheckAnnotation,
    CheckRunConclusion,
    CheckRunOutput,
)


class _CodePosition(BaseModel):
    column: int
    row: int


class _RuffEditSuggestion(BaseModel):
    content: str
    location: _CodePosition
    end_location: _CodePosition


class _RuffFixSuggestion(BaseModel):
    applicability: str
    edits: list[_RuffEditSuggestion]
    message: str


class _RuffJSONError(BaseModel):
    cell: Any | None  # not sure of its type, but fairly sure it's irrelevant for us
    code: str
    location: _CodePosition
    end_location: _CodePosition
    filename: Path
    fix: _RuffFixSuggestion | None
    message: str
    noqa_row: int
    url: str


def _format_annotations_for_ruff_json_output(
    json_output_fp: Path,
    local_repo_base: Path,
    annotation_level: AnnotationLevel,
) -> Iterable[CheckAnnotation]:
    """Generate annotations for the ruff's output when run with output-format=json.

    :param json_output_fp: filepath to the full json output from ruff
    :param local_repo_base: local repository base path, for deriving repo-relative paths
    """
    with json_output_fp.open("r", encoding="utf-8") as json_file:
        json_content = json.load(json_file)

    for error_dict in json_content:
        ruff_err: _RuffJSONError = _RuffJSONError.model_validate(error_dict)
        err_is_on_one_line: bool = ruff_err.location.row == ruff_err.end_location.row
        # Note: github annotations have markdown support -> let's hyperlink the err code
        # this will look like "D100: undocumented public module" with the D100 clickable
        title: str = f"[{ruff_err.code}] {ruff_err.url.split('/')[-1]}"
        raw_details: str | None = None
        if ruff_err.fix:
            raw_details = (
                f"Ruff suggests the following fix: {ruff_err.fix.message}\n"
                + "\n".join(
                    f"Replace line {edit.location.row}, column {edit.location.column} "
                    f"to line {edit.end_location.row}, column "
                    f"{edit.end_location.column} with:\n{edit.content}"
                    for edit in ruff_err.fix.edits
                )
            )
        message = (
            ruff_err.message + "\n\n" + "See " + ruff_err.url + " for more information."
        )
        yield CheckAnnotation(
            annotation_level=annotation_level,
            start_line=ruff_err.location.row,
            start_column=ruff_err.location.column if err_is_on_one_line else None,
            end_line=ruff_err.end_location.row,
            end_column=ruff_err.end_location.column if err_is_on_one_line else None,
            path=str(ruff_err.filename.relative_to(local_repo_base)),
            message=message,
            raw_details=raw_details,
            title=title,
        )


def format_ruff_check_run_output(
    json_output_fp: Path,
    local_repo_base: Path,
) -> tuple[CheckRunOutput, CheckRunConclusion]:
    """Generate high level results, to be shown on the "Checks" tab."""
    with json_output_fp.open("r", encoding="utf-8") as json_file:
        json_content = json.load(json_file)

    issues: list[str] = []
    issue_codes: set[str] = set()
    for ruff_err_json in json_content:
        ruff_err = _RuffJSONError.model_validate(ruff_err_json)
        if ruff_err.code in issue_codes:
            continue
        issue_codes.add(ruff_err.code)
        # Note: github annotations have markdown support -> let's hyperlink the err code
        # this will look like "D100: undocumented public module" with the D100 clickable
        issues.append(
            f"> **[[{ruff_err.code}]({ruff_err.url})] {ruff_err.url.split('/')[-1]}**",
        )

    # Use warning level for annotations (since nothing broke, but still needs fixing)
    annotations: list[CheckAnnotation] = list(
        _format_annotations_for_ruff_json_output(
            json_output_fp,
            local_repo_base,
            AnnotationLevel.WARNING,
        ),
    )
    # be strict with the conclusion - disapprove if there are any ruff errors whatsoever
    if annotations:
        conclusion = CheckRunConclusion.ACTION_REQUIRED
        title = f"Ruff found {len(issue_codes)} issues."
        summary: str = (
            "Ruff found the following issues:\n" + "\n".join(issues) + "\n\n"
            "Click the error codes to check out why ruff thinks these are bad, or go "
            "to the source files to check out the annotations on the offending code."
        )
    else:
        conclusion = CheckRunConclusion.SUCCESS
        title = "Ruff found no issues."
        summary = "Nice work!"

    return (
        CheckRunOutput(title=title, summary=summary, annotations=annotations),
        conclusion,
    )
