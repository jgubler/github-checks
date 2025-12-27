"""Formatter to process SARIF output and yield GitHub annotations."""

import json
from collections.abc import Iterable
from pathlib import Path

from pysarif import Region, ReportingDescriptor, Result, load_from_dict

from github_checks.formatters.utils import filter_for_checksignore, get_conclusion
from github_checks.models import (
    AnnotationLevel,
    CheckAnnotation,
    CheckRunConclusion,
    CheckRunOutput,
)


def get_rule_name(full_rule: ReportingDescriptor) -> str:
    """Extract the rule name from a SARIF ReportingDescriptor.

    :param full_rule: SARIF ReportingDescriptor for the rule
    :return: rule name as a string
    """
    if full_rule.name:
        # name should be in full_rule.name, sadly pysarif often fails to parse it
        return str(full_rule.name)
    if full_rule.help_uri:
        # if we have a URI for the rule, the final part is usually the rule name
        return str(full_rule.help_uri.split("/")[-1])
    return "Unknown Rule"


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
    tool_rules: list[ReportingDescriptor] = run.tool.driver.rules or []

    for result in run.results or []:
        if not (
            full_rule := next(
                (rule for rule in tool_rules if rule.id == result.rule_id),
                None,
            )
        ):
            # This result's rule is not in the tool's rules list, should never occur
            continue

        title, message, raw_details = get_annotation_texts_from_sarif_result(
            result,
            full_rule,
        )

        for location in result.locations or []:
            region: Region | None
            try:
                filepath = Path(
                    location.physical_location.artifact_location.uri.partition(":")[2],  # pyright: ignore[reportOptionalMemberAccess]
                )
                region = location.physical_location.region  # pyright: ignore[reportOptionalMemberAccess]
            except AttributeError:
                # error without any sensible location, skip it
                continue
            if not (region and region.start_line and region.end_line):
                # error without any sensible location, skip it
                continue
            err_is_on_one_line: bool = region.start_line == region.end_line

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


def get_annotation_texts_from_sarif_result(  # noqa: C901, PLR0912
    result: Result,
    full_rule: ReportingDescriptor,
) -> tuple[str, str, str | None]:
    """Extract title, message, and raw_details for a SARIF result annotation.

    :param result: SARIF result object
    :param full_rule: SARIF ReportingDescriptor for the rule that triggered this result
    :return: tuple of (title, message, raw_details)
    """
    rule_name: str
    if full_rule.name:
        # name should be in full_rule.name, sadly pysarif often fails to parse it
        rule_name = full_rule.name
    elif full_rule.help_uri:
        # if we have a URI for the rule, the final part is usually the rule name
        rule_name = full_rule.help_uri.split("/")[-1]
    else:
        rule_name = "Unknown Rule"

    # Note: github annotations do not have markdown support, only check run summaries do
    title: str = f"[{result.rule_id}]: {rule_name}" if result.rule_id else rule_name

    raw_details: str | None = None

    if full_rule.full_description and full_rule.full_description.text:
        raw_details = (
            "Background for this rule per tool's documentation:\n> "
            + "\n> ".join(full_rule.full_description.text.split("\n"))
        )
    elif full_rule.full_description and full_rule.full_description.markdown:
        # we'll only use markdown if plain text is not available, as with the raw detail
        # display of comments not supporting markdown, it's less readable than plain
        raw_details = (
            "Background for this rule per tool's documentation:\n> "
            + "\n> ".join(full_rule.full_description.markdown.split("\n"))
        )
    message: str | None = None
    if result.message.markdown:
        message = result.message.markdown
    elif result.message.text:
        message = result.message.text

    message_add = ""
    if raw_details:
        message_add += "the raw details of this comment"
    if result.rule_id:
        if message_add:
            message_add += " or "
        rule_uri = f"({full_rule.help_uri}) " if full_rule.help_uri else ""
        message_add += (
            f"documentation for rule {result.rule_id} {rule_uri}for more information."
        )
    if message_add:
        message = f"{message}\n\n" if message else ""
        message += f"See {message_add}"
    if not message:
        message = "No additional information provided."

    raw_details = None

    if full_rule.full_description and full_rule.full_description.text:
        raw_details = (
            "Background for this rule per tool's documentation:\n> "
            + "\n> ".join(full_rule.full_description.text.split("\n"))
        )

    return title, message, raw_details


def format_sarif_check_run_output(
    json_output_fp: Path,
    local_repo_base: Path,
    ignored_globs: list[str] | None = None,
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
    issues: list[str] = []
    for rule in sarif_output.runs[0].tool.driver.rules or []:
        rule_id_str = (
            f"[[{rule.id}]({rule.help_uri})]" if rule.help_uri else f"[{rule.id}]"
        )
        full_desc: str | None = (
            rule.full_description.markdown
            if rule.full_description and rule.full_description.markdown
            else rule.full_description.text
            if rule.full_description and rule.full_description.text
            else None
        )

        issue_str = f"##{rule_id_str} {get_rule_name(rule)}\n"
        if full_desc:
            issue_str += (
                f"Background for this rule per {tool_name}'s documentation:\n> "
            )
            issue_str += "\n> ".join(full_desc.split("\n")) + "\n"
        issues.append(issue_str)

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

    if annotations:
        summary: str = (
            "\n".join(issues) + "\n\n"
            "Navigate to the source files via the annotations below to see the "
            "offending code."
        )
        if conclusion == CheckRunConclusion.ACTION_REQUIRED:
            title = f"{tool_name} found issues with {len(issues)} rules."
        else:
            title = f"{tool_name} only found issues in ignored files."
    else:
        title = f"{tool_name} found no issues."
        summary = "Nice work!"

    return (
        CheckRunOutput(title=title, summary=summary, annotations=annotations),
        conclusion,
    )
