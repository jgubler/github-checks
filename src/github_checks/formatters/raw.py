"""Formatter to process raw output and yield an annotation-less summary."""

from pathlib import Path

from github_checks.models import (
    CheckRunConclusion,
    CheckRunOutput,
)


def format_raw_check_run_output(
    output_fp: Path,
    _: Path,
    __: list[str] | None = None,
    *,
    ignore_verdict_only: bool = False,  # noqa: ARG001
) -> tuple[CheckRunOutput, CheckRunConclusion]:
    """Generate output for raw checks, to be shown on the "Checks" tab."""
    if not output_fp.exists():
        # If the output file does not exist, we consider it a success
        conclusion = CheckRunConclusion.SUCCESS
        raw_output = ""
    else:
        with output_fp.open("r", encoding="utf-8") as f:
            raw_output = f.read().strip()
            # If there is no output, we consider it a success
            # If there is output, we consider it an action required
            conclusion = (
                CheckRunConclusion.SUCCESS
                if raw_output == ""
                else CheckRunConclusion.ACTION_REQUIRED
            )

    # Process the raw output and create the CheckRunOutput and CheckRunConclusion
    output = CheckRunOutput(
        title="Raw Check Results",
        summary=raw_output,
        annotations=[],
    )

    return output, conclusion
