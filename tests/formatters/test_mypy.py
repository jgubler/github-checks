import json
import tempfile
from pathlib import Path
from github_checks.formatters.mypy import format_mypy_check_run_output
from github_checks.models import CheckRunConclusion, CheckRunOutput, AnnotationLevel


def sample_mypy_output(repo_root: Path, json_fp: Path) -> None:
    mypy_output = [
        {
            "file": str(repo_root / "src/github_checks/formatters/ruff.py"),
            "line": 133,
            "column": 11,
            "message": 'Incompatible return value type (got "tuple[CheckRunOutput, CheckRunConclusion]", expected "tuple[CheckRunOutput]")',
            "hint": None,
            "code": "return-value",
            "severity": "error",
        },
        {
            "file": str(repo_root / "src/github_checks/cli.py"),
            "line": 20,
            "column": 4,
            "message": 'Dict entry 0 has incompatible type "str": "Callable[[Path, Path], tuple[CheckRunOutput]]"; expected "str": "Callable[[Path, Path], tuple[CheckRunOutput, CheckRunConclusion]]"',
            "hint": None,
            "code": "dict-item",
            "severity": "error",
        },
    ]
    with json_fp.open("w", encoding="utf-8") as f:
        # Write each mypy error as an individual JSON line, matching mypy's format
        f.writelines(json.dumps(mypy_line) + "\n" for mypy_line in mypy_output)


def test_format_mypy_check_run_output_with_issues() -> None:
    sample_output_fp = Path(tempfile.NamedTemporaryFile(delete=False).name)
    sample_mypy_output(Path(__file__).parent, sample_output_fp)
    output, conclusion = format_mypy_check_run_output(
        sample_output_fp, Path(__file__).parent
    )
    assert isinstance(output, CheckRunOutput)
    assert conclusion == CheckRunConclusion.ACTION_REQUIRED
    assert "Mypy found" in output.title
    assert "return-value" in output.summary
    assert "dict-item" in output.summary
    assert len(output.annotations) == 2
    for annotation in output.annotations:
        assert annotation.annotation_level == AnnotationLevel.WARNING
        assert annotation.path
        assert annotation.message
        assert annotation.title


def test_format_mypy_check_run_output_no_issues() -> None:
    empty_json_fp = Path(tempfile.NamedTemporaryFile(delete=False).name)
    empty_json_fp.write_text("")
    output, conclusion = format_mypy_check_run_output(
        empty_json_fp, Path(__file__).parent
    )
    assert isinstance(output, CheckRunOutput)
    assert conclusion == CheckRunConclusion.SUCCESS
    assert "Mypy found no issues" in output.title
    assert output.summary == "Nice work!"
    assert len(output.annotations) == 0
