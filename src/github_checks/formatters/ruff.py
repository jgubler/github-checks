"""Formatter to process ruff output and yield GitHub annotations."""

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from github_checks.models import AnnotationLevel, ChecksAnnotation


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


def format_ruff_json_output(
    json_dump: str,
    local_repo_base: Path,
) -> Iterable[ChecksAnnotation]:
    """Generate annotations for the ruff's output when run with output-format=json.

    :param json_dump: the full json output from ruff, as a string
    :param local_repo_base: local repository base path, for deriving repo-relative paths
    """
    for error_dict in json.loads(json_dump):
        ruff_err: _RuffJSONError = _RuffJSONError.model_validate(error_dict)
        err_is_on_one_line: bool = ruff_err.location.row == ruff_err.end_location.row
        # Note: github annotations have markdown support -> let's hyperlink the err code
        # this will look like "D100: undocumented public module" with the D100 clickable
        title: str = f"[{ruff_err.code}]({ruff_err.url}): {ruff_err.url.split('/')[-1]}"
        raw_details: str | None = None
        if ruff_err.fix:
            raw_details = (
                "Ruff suggests the following fix: {ruff_err.fix.message}\n"
                + "\n".join(
                    f"Replace line {edit.location.row}, column {edit.location.column} "
                    "to line {edit.end_location.row}, column {edit.end_location.column}"
                    " with:\n{edit.content}"
                    for edit in ruff_err.fix.edits
                )
            )
        yield ChecksAnnotation(
            annotation_level=AnnotationLevel.FAILURE,
            start_line=ruff_err.location.row,
            start_column=ruff_err.location.column if err_is_on_one_line else None,
            end_line=ruff_err.end_location.row,
            end_column=ruff_err.end_location.column if err_is_on_one_line else None,
            filepath=ruff_err.filename.relative_to(local_repo_base),
            message=ruff_err.message,
            raw_details=raw_details,
            title=title,
        )
