"""Tests for the pyright formatter output used in GitHub Checks."""

import json
import tempfile
from pathlib import Path
from time import time
from typing import Any

from github_checks.formatters.pyright import format_pyright_check_run_output
from github_checks.models import AnnotationLevel, CheckRunConclusion, CheckRunOutput

# ruff: noqa: S101, D103, SIM115, INP001


def sample_pyright_output(repo_root: Path, json_fp: Path) -> None:
    pyright_output: dict[str, Any] = {
        "version": "1.1.407",
        "time": str(int(time())),
        "generalDiagnostics": [
            {
                "file": str(repo_root / "src/github_checks/cli.py"),
                "severity": "error",
                "message": 'Import "configargparse" could not be resolved',
                "range": {
                    "start": {"line": 9, "character": 5},
                    "end": {"line": 9, "character": 19},
                },
                "rule": "reportMissingImports",
            },
            {
                "file": str(repo_root / "src/github_checks/formatters/pyright.py"),
                "severity": "error",
                "message": 'No parameter named "ignore_verdict_only"',
                "range": {
                    "start": {"line": 179, "character": 8},
                    "end": {"line": 179, "character": 27},
                },
                "rule": "reportCallIssue",
            },
        ],
        "summary": {
            "filesAnalyzed": 12,
            "errorCount": 9,
            "warningCount": 1,
            "informationCount": 0,
            "timeInSec": 0.379,
        },
    }
    with json_fp.open("w", encoding="utf-8") as f:
        json.dump(pyright_output, f)


def test_format_pyright_check_run_output_with_issues() -> None:
    sample_output_fp = Path(tempfile.NamedTemporaryFile(delete=False).name)
    sample_pyright_output(Path(__file__).parent, sample_output_fp)
    output, conclusion = format_pyright_check_run_output(
        sample_output_fp,
        Path(__file__).parent.parent.parent,
        ignored_globs=None,
        ignore_verdict_only=False,
    )
    assert isinstance(output, CheckRunOutput)
    assert conclusion == CheckRunConclusion.ACTION_REQUIRED
    assert output.title is not None
    assert "Pyright found" in output.title
    assert "reportMissingImports" in output.summary
    assert "reportCallIssue" in output.summary
    assert output.annotations is not None
    assert len(output.annotations) == 2  # noqa: PLR2004
    for annotation in output.annotations:
        assert annotation.annotation_level == AnnotationLevel.FAILURE
        assert annotation.path
        assert annotation.message
        assert annotation.title
