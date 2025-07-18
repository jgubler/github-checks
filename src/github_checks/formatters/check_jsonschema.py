"""Formatter to process check-jsonschema output and yield GitHub annotations."""

import json
from pathlib import Path

from pydantic import BaseModel

from github_checks.formatters.utils import filter_for_checksignore, get_conclusion
from github_checks.models import (
    AnnotationLevel,
    CheckAnnotation,
    CheckRunConclusion,
    CheckRunOutput,
)


class _CheckJsonSchemaSubError(BaseModel):
    path: str
    message: str


class _CheckJsonSchemaError(BaseModel):
    """Error model for JSON schema validation errors."""

    filename: str
    path: str
    message: str
    has_sub_errors: bool
    best_match: _CheckJsonSchemaSubError | None = None
    best_deep_match: _CheckJsonSchemaSubError | None = None
    num_sub_errors: int | None = None
    sub_errors: list[_CheckJsonSchemaSubError] | None = None


def get_err_loc(filename: Path, path: str) -> tuple[int, int, int]:
    """Get the line number of the error in the file."""
    # path looks something like "@.attributeA.attributeB"
    offending_attr_parts = path.split(".")[1:]
    num_attr_parts = len(offending_attr_parts)
    if num_attr_parts == 0:
        return 0, 0, 0  # No path to validate, error was global (e.g. missing field)
    num_validated_parts = 0

    with filename.open("r", encoding="utf-8") as file:
        for i, line in enumerate(file.readlines()):
            if (
                line.strip()
                .strip('"')
                .startswith(offending_attr_parts[num_validated_parts])
            ):
                num_validated_parts += 1
            if num_validated_parts == num_attr_parts:
                # If all parts of the path are found, return the line number with col
                column = line.index(offending_attr_parts[-1])
                return i, column, len(line) - 1
    return 0, 0, 0


def format_jsonschema_check_run_output(
    json_output_fp: Path,
    local_repo_base: Path,
    ignore_globs: list[str] | None,
    ignore_verdict_only: bool,
) -> tuple[CheckRunOutput, CheckRunConclusion]:
    """Generate high level results, to be shown on the "Checks" tab."""
    with json_output_fp.open("r", encoding="utf-8") as json_file:
        file_content = json_file.read()
    if not file_content.strip() or file_content in ("{}", "[]"):
        errors = []
    else:
        errors = json.loads(file_content).get("errors", [])

    annotations = []

    for error_dict in errors:
        json_err: _CheckJsonSchemaError = _CheckJsonSchemaError.model_validate(
            error_dict,
        )

        err_line, err_start_column, err_end_column = get_err_loc(
            Path(json_err.filename),
            json_err.path,
        )
        message = json_err.message
        if json_err.has_sub_errors and json_err.best_match:
            message += "\n" + json_err.best_match.message
        annotations.append(
            CheckAnnotation(
                path=json_err.filename,
                start_line=err_line + 1,  # GitHub uses 1-based indexing
                end_line=err_line + 1,  # GitHub uses 1-based indexing
                start_column=err_start_column + 1,  # GitHub uses 1-based indexing
                end_column=err_end_column + 1,  # GitHub uses 1-based indexing
                annotation_level=AnnotationLevel.WARNING,
                message=message,
                title=f"Schema validation error on {json_err.path}",
            ),
        )

    # Filter out ignored files from the verdict / annotations (depending on settings)
    if ignore_globs:
        filtered_annotations: list[CheckAnnotation] = list(
            filter_for_checksignore(
                annotations,
                ignore_globs,
                local_repo_base,
            )
        )
        conclusion = get_conclusion(filtered_annotations)
        if not ignore_verdict_only:
            annotations = filtered_annotations
    else:
        conclusion = get_conclusion(annotations)

    if annotations:
        if conclusion == CheckRunConclusion.ACTION_REQUIRED:
            title = f"JSON Schema validation found {len(annotations)} issues"
            summary = (
                "The schema validation found the following issues in JSON/YAML files:"
            )
        else:
            title = "JSON Schema validation only found issues in ignored files"
            summary = (
                "The JSON schema validation found issues in JSON/YAML files. "
                "See the annotations below for details."
            )
    else:
        title = "JSON Schema validation found no issues"
        summary = (
            "The JSON schema validation did not find any issues in JSON/YAML files."
        )

    return (
        CheckRunOutput(
            title=title,
            summary=summary,
            annotations=annotations,
        ),
        conclusion,
    )
