"""Formatter to process raw output and yield an annotation-less summary."""

from pathlib import Path

from github_checks.models import (
    CheckRunConclusion,
    CheckRunOutput,
)

# GitHub's max length for POST bodies is around 65k bytes
# Use a smaller limit to leave room for other fields and multi-byte unicode characters
MAX_OUTPUT_LENGTH = 30000


def format_raw_check_run_output(
    json_output_fp: Path,
    local_repo_base: Path,  # noqa: ARG001
    ignored_globs: list[str] | None = None,  # noqa: ARG001
    *,
    mute_ignored_annotations: bool = False,  # noqa: ARG001
) -> tuple[CheckRunOutput, CheckRunConclusion]:
    """Generate output for raw checks, to be shown on the "Checks" tab."""
    if not json_output_fp.exists():
        # If the output file does not exist, we consider it a success
        conclusion = CheckRunConclusion.SUCCESS
        raw_output = ""
    else:
        with json_output_fp.open("r", encoding="utf-8") as f:
            raw_output = f.read().strip()
            # If there is no output, we consider it a success
            # If there is output, we consider it an action required
            conclusion = (
                CheckRunConclusion.SUCCESS
                if raw_output == ""
                else CheckRunConclusion.ACTION_REQUIRED
            )

    if len(raw_output) > MAX_OUTPUT_LENGTH:
        summary = (
            raw_output[:MAX_OUTPUT_LENGTH]
            + "\n\n... (truncated output, see full text log for details) ..."
        )
    else:
        summary = raw_output

    # Process the raw output and create the CheckRunOutput and CheckRunConclusion
    output = CheckRunOutput(
        title="Raw Check Results",
        summary=summary,
        annotations=[],
    )

    return output, conclusion
