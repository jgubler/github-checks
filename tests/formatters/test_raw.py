"""Test the raw formatter for check runs."""

import tempfile
from pathlib import Path

from github_checks.formatters.raw import format_raw_check_run_output
from github_checks.models import CheckRunConclusion, CheckRunOutput

# ruff: noqa: S101, D103, SIM115, INP001


def sample_raw_output(_: Path, raw_out_fp: Path) -> None:
    raw_output = "This went very badly, the worst of all time, some say."
    with raw_out_fp.open("w", encoding="utf-8") as f:
        f.write(raw_output)


def test_format_raw_check_run_output_with_issues() -> None:
    sample_output_fp = Path(tempfile.NamedTemporaryFile(delete=False).name)
    sample_raw_output(Path(__file__).parent.parent.parent, sample_output_fp)
    output, conclusion = format_raw_check_run_output(
        sample_output_fp,
        Path(__file__).parent.parent.parent,
    )
    assert isinstance(output, CheckRunOutput)
    assert conclusion == CheckRunConclusion.ACTION_REQUIRED
    assert "Raw Check Results" in output.title
    assert "This went very badly" in output.summary
    assert len(output.annotations) == 0  # Raw formatter does not produce annotations


def test_format_raw_check_run_output_no_issues() -> None:
    empty_output_fp = Path(tempfile.NamedTemporaryFile(delete=False).name)
    empty_output_fp.write_text("")
    output, conclusion = format_raw_check_run_output(
        empty_output_fp,
        Path(__file__).parent,
    )
    assert isinstance(output, CheckRunOutput)
    assert conclusion == CheckRunConclusion.SUCCESS
    assert "Raw Check Results" in output.title
    assert output.summary == ""
    assert len(output.annotations) == 0  # Raw formatter does not produce annotations


def test_format_raw_check_run_no_output_file() -> None:
    # Test with a non-existent file
    non_existent_fp = Path("non_existent_output.txt")
    output, conclusion = format_raw_check_run_output(
        non_existent_fp,
        Path(__file__).parent,
    )
    assert isinstance(output, CheckRunOutput)
    assert conclusion == CheckRunConclusion.SUCCESS
    assert "Raw Check Results" in output.title
    assert output.summary == ""
    assert len(output.annotations) == 0  # Raw formatter does not produce annotations
