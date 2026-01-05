"""Tests for the Ruff formatter output used in GitHub Checks."""

import json
import tempfile
from pathlib import Path

from github_checks.formatters.ruff import format_ruff_check_run_output
from github_checks.models import AnnotationLevel, CheckRunConclusion, CheckRunOutput

# ruff: noqa: S101, D103, SIM115, INP001

REPO_ROOT = Path(__file__).parent.parent.parent
RUFF_OUTPUT = [
    {
        "cell": None,
        "code": "D100",
        "location": {"row": 1, "column": 1},
        "end_location": {"row": 1, "column": 1},
        "filename": str(REPO_ROOT / "src" / "github_checks" / "formatters" / "mypy.py"),
        "fix": None,
        "message": "Missing docstring in public module",
        "noqa_row": 1,
        "url": "https://docs.astral.sh/ruff/rules/D100/",
    },
    {
        "cell": None,
        "code": "LOG015",
        "location": {"row": 83, "column": 9},
        "end_location": {"row": 83, "column": 46},
        "filename": str(REPO_ROOT / "src" / "github_checks" / "github_api.py"),
        "fix": None,
        "message": "`exception()` call on root logger",
        "noqa_row": 83,
        "url": "https://docs.astral.sh/ruff/rules/LOG015/",
    },
]


def test_format_ruff_check_run_output_with_issues() -> None:
    sample_output_fp = Path(tempfile.NamedTemporaryFile(delete=False).name)

    with sample_output_fp.open("w", encoding="utf-8") as f:
        json.dump(RUFF_OUTPUT, f)

    output, conclusion = format_ruff_check_run_output(
        sample_output_fp,
        REPO_ROOT,
        ignored_globs=None,
        mute_ignored_annotations=True,
    )
    assert isinstance(output, CheckRunOutput)
    assert conclusion == CheckRunConclusion.ACTION_REQUIRED
    assert output.title is not None
    assert "Ruff found" in output.title
    assert "D100" in output.summary
    assert "LOG015" in output.summary
    assert output.annotations is not None
    assert len(output.annotations) == 2  # noqa: PLR2004
    for annotation in output.annotations:
        assert annotation.annotation_level == AnnotationLevel.WARNING
        assert annotation.path
        assert annotation.message
        assert annotation.title


def test_format_ruff_check_run_output_with_issues_ignored() -> None:
    sample_output_fp = Path(tempfile.NamedTemporaryFile(delete=False).name)

    with sample_output_fp.open("w", encoding="utf-8") as f:
        json.dump(RUFF_OUTPUT, f)

    output, conclusion = format_ruff_check_run_output(
        sample_output_fp,
        REPO_ROOT,
        ignored_globs=["/src/github_checks/"],
        mute_ignored_annotations=False,
    )
    assert isinstance(output, CheckRunOutput)
    assert conclusion == CheckRunConclusion.SUCCESS
    assert output.title is not None
    assert "Ruff only found" in output.title
    assert "D100" in output.summary
    assert "LOG015" in output.summary
    assert output.annotations is not None
    assert len(output.annotations) == 2  # noqa: PLR2004
    for annotation in output.annotations:
        assert annotation.annotation_level == AnnotationLevel.WARNING
        assert annotation.path
        assert annotation.message
        assert annotation.title


def test_format_ruff_check_run_output_no_issues() -> None:
    empty_json_fp = Path(tempfile.NamedTemporaryFile(delete=False).name)
    empty_json_fp.write_text("[]")
    output, conclusion = format_ruff_check_run_output(
        empty_json_fp,
        REPO_ROOT,
        ignored_globs=None,
        mute_ignored_annotations=True,
    )
    assert isinstance(output, CheckRunOutput)
    assert conclusion == CheckRunConclusion.SUCCESS
    assert output.title is not None
    assert "no issues" in output.title.lower()
    assert output.summary == "Nice work!"
    assert output.annotations == []
