import json
from pathlib import Path
import tempfile

from github_checks.formatters.sarif import format_sarif_check_run_output
from github_checks.models import AnnotationLevel, CheckRunConclusion, CheckRunOutput


REPO_ROOT = Path(__file__).parent.parent.parent

SARIF_OUT = {
    "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
    "runs": [
        {
            "results": [
                {
                    "level": "error",
                    "locations": [
                        {
                            "physicalLocation": {
                                "artifactLocation": {
                                    "uri": "file://" + str(
                                REPO_ROOT / "src" / "github_checks" / "github_api.py"
                                    )
                                },
                                "region": {
                                    "endColumn": 46,
                                    "endLine": 83,
                                    "startColumn": 9,
                                    "startLine": 83,
                                },
                            }
                        }
                    ],
                    "message": {"text": "`exception()` call on root logger"},
                    "ruleId": "LOG015",
                },
                {
                    "level": "error",
                    "locations": [
                        {
                            "physicalLocation": {
                                "artifactLocation": {
                                    "uri": "file://" + str(
                                REPO_ROOT / "src" / "github_checks" / "github_api.py"
                                    )                                },
                                "region": {
                                    "endColumn": 14,
                                    "endLine": 185,
                                    "startColumn": 13,
                                    "startLine": 181,
                                },
                            }
                        }
                    ],
                    "message": {"text": "`warning()` call on root logger"},
                    "ruleId": "LOG015",
                },
            ],
            "tool": {
                "driver": {
                    "informationUri": "https://github.com/astral-sh/ruff",
                    "name": "ruff",
                    "rules": [
                        {
                            "fullDescription": {
                                "text": '## What it does\nChecks for usages of the following `logging` top-level functions:\n`debug`, `info`, `warn`, `warning`, `error`, `critical`, `log`, `exception`.\n\n## Why is this bad?\nUsing the root logger causes the messages to have no source information,\nmaking them less useful for debugging.\n\n## Example\n```python\nimport logging\n\nlogging.info("Foobar")\n```\n\nUse instead:\n```python\nimport logging\n\nlogger = logging.getLogger(__name__)\nlogger.info("Foobar")\n```\n'
                            },
                            "help": {"text": "`{}()` call on root logger"},
                            "helpUri": "https://docs.astral.sh/ruff/rules/root-logger-call",
                            "id": "LOG015",
                            "properties": {
                                "id": "LOG015",
                                "kind": "flake8-logging",
                                "name": "root-logger-call",
                                "problem.severity": "error",
                            },
                            "shortDescription": {"text": "`{}()` call on root logger"},
                        }
                    ],
                    "version": "0.12.2",
                }
            },
        }
    ],
    "version": "2.1.0",
}


def test_format_sarif_check_run_output_with_issues() -> None:
    sample_output_fp = Path(tempfile.NamedTemporaryFile(delete=False).name)

    with sample_output_fp.open("w", encoding="utf-8") as f:
        json.dump(SARIF_OUT, f)

    output, conclusion = format_sarif_check_run_output(
        sample_output_fp,
        REPO_ROOT,
    )
    assert isinstance(output, CheckRunOutput)
    assert conclusion == CheckRunConclusion.ACTION_REQUIRED
    assert "ruff found" in output.title
    assert "LOG015" in output.summary
    assert len(output.annotations) == 2
    for annotation in output.annotations:
        assert annotation.annotation_level == AnnotationLevel.WARNING
        assert annotation.path
        assert annotation.message
        assert annotation.title


def test_format_ruff_check_run_output_no_issues() -> None:
    text = SARIF_OUT.copy()
    text["runs"][0]["results"] = []  # type: ignore[index]
    text["runs"][0]["tool"]["driver"]["rules"] = []  # type: ignore[index]
    with Path(tempfile.NamedTemporaryFile(delete=False).name) as tempfile_fp:
        with tempfile_fp.open("w", encoding="utf-8") as empty_json:
            json.dump(text, empty_json)
        output, conclusion = format_sarif_check_run_output(
            tempfile_fp, REPO_ROOT
        )
    assert isinstance(output, CheckRunOutput)
    assert conclusion == CheckRunConclusion.SUCCESS
    assert "no issues" in output.title.lower()
    assert output.summary == "Nice work!"
    assert output.annotations == []