"""Formatter to process SARIF output and yield GitHub annotations."""

import json
from collections.abc import Iterable
from pathlib import Path

from pysarif import load_from_dict

from github_checks.formatters.utils import filter_for_checksignore, get_conclusion
from github_checks.models import (
    AnnotationLevel,
    CheckAnnotation,
    CheckRunConclusion,
    CheckRunOutput,
)


def _format_annotations_for_sarif_json_output(
    json_output_fp: Path,
    local_repo_base: Path,
    annotation_level: AnnotationLevel,
) -> Iterable[CheckAnnotation]:
    """Generate annotations for any SARIF json output.

    :param json_output_fp: filepath to the full SARIF json output
    :param local_repo_base: local repository base path, for deriving repo-relative paths
    """
    with json_output_fp.open("r", encoding="utf-8") as json_file:
        json_content = json.load(json_file)

    # Implicitly validates the JSON content against SARIF schema
    sarif_output = load_from_dict(json_content)
    if not sarif_output.runs:
        return

    # We only support processing one run in the SARIF output for now
    run = sarif_output.runs[0]
    tool_rules = run.tool.driver.rules

    for result in run.results:
        for location in result.locations:
            try:
                filepath = Path(
                    location.physical_location.artifact_location.uri.partition(":")[2],
                )
            except AttributeError:  # noqa: PERF203
                # error without any location, skip it
                break
        region = location.physical_location.region
        err_is_on_one_line: bool = region.start_line == region.end_line
        full_rule = next(rule for rule in tool_rules if rule.id == result.rule_id)

        # Note: github annotations have markdown support -> let's hyperlink the err code
        # this will look like "D100: undocumented public module" with the D100 clickable
        # the name should be in full_rule.properties.name, but pysarif fails to parse it
        rule_name = full_rule.help_uri.split("/")[-1]
        title: str = f"[{result.rule_id}] {rule_name}"
        raw_details = "About the rule:\n\n" + full_rule.full_description.text
        message = (
            result.message.text
            + "\n\nSee "
            + full_rule.help_uri
            + " for more information."
        )
        yield CheckAnnotation(
            annotation_level=annotation_level,
            start_line=region.start_line,
            start_column=region.start_column if err_is_on_one_line else None,
            end_line=region.end_line,
            end_column=region.end_column if err_is_on_one_line else None,
            path=str(filepath.relative_to(local_repo_base)),
            message=message,
            raw_details=raw_details,
            title=title,
        )


def format_sarif_check_run_output(
    json_output_fp: Path,
    local_repo_base: Path,
    ignore_globs: list[str] | None = None,
    *,
    ignore_verdict_only: bool = False,
) -> tuple[CheckRunOutput, CheckRunConclusion]:
    """Generate high level results, to be shown on the "Checks" tab."""
    with json_output_fp.open("r", encoding="utf-8") as json_file:
        json_content = json.load(json_file)

    # Implicitly validates the JSON content against SARIF schema
    sarif_output = load_from_dict(json_content)
    tool_name = (
        sarif_output.runs[0].tool.driver.name if sarif_output.runs else "Unknown"
    )
    # Use warning level for annotations (since nothing broke, but still needs fixing)
    annotations: list[CheckAnnotation] = list(
        _format_annotations_for_sarif_json_output(
            json_output_fp,
            local_repo_base,
            AnnotationLevel.WARNING,
        ),
    )
    if not annotations:
        return (
            CheckRunOutput(
                title=tool_name + " found no issues.",
                summary="Nice work!",
                annotations=[],
            ),
            CheckRunConclusion.SUCCESS,
        )

    # the following will yield something like this in markdown:
    # [LOG015](https://docs.astral.sh/ruff/rules/root-logger-call') root-logger-call
    # the name _should_ be in full_rule.properties.name, but pysarif fails to parse it,
    # so we use the last part of the help_uri instead, which is identical thankfully
    issues = [
        f"## [[{rule.id}]({rule.help_uri})] {rule.help_uri.split('/')[-1]}\n"
        f"Background for this rule per {tool_name}'s documentation:\n> "
        + "\n> ".join(rule.full_description.text.split("\n"))
        + "\n"
        for rule in sarif_output.runs[0].tool.driver.rules
    ]

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
        summary: str = (
            "\n".join(issues) + "\n\n"
            "Navigate to the source files via the annotations below to see the "
            "offending code."
        )
        if conclusion == CheckRunConclusion.ACTION_REQUIRED:
            title = f"{tool_name} found issues with {len(issues)} rules."
        elif annotations:
            title = f"{tool_name} only found issues in ignored files."
    else:
        title = f"{tool_name} found no issues."

    return (
        CheckRunOutput(title=title, summary=summary, annotations=annotations),
        conclusion,
    )
