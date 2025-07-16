import json
from pathlib import Path
import tempfile

from github_checks.formatters.check_jsonschema import format_jsonschema_check_run_output
from github_checks.models import AnnotationLevel, CheckRunConclusion, CheckRunOutput


CHECK_JSONSCHEMA_OUTPUT = {
  "status": "fail",
  "errors": [
    {
      "filename": "tests/json_validation/invalid_user.json",
      "path": "$",
      "message": "'email' is a required property",
      "has_sub_errors": False
    },
    {
      "filename": "tests/json_validation/invalid_user.json",
      "path": "$.age",
      "message": "'thirty' is not of type 'integer'",
      "has_sub_errors": False
    },
    {
      "filename": "tests/json_validation/invalid_user.json",
      "path": "$.interests",
      "message": "20 is not of type 'array'",
      "has_sub_errors": False
    }
  ],
  "parse_errors": []
}



def test_format_check_jsonschema_check_run_output_with_issues() -> None:
    sample_output_fp = Path(tempfile.NamedTemporaryFile(delete=False).name)

    with sample_output_fp.open("w", encoding="utf-8") as f:
        json.dump(CHECK_JSONSCHEMA_OUTPUT, f)

    output, conclusion = format_jsonschema_check_run_output(
        sample_output_fp,
        Path(__name__).parent,
    )
    assert isinstance(output, CheckRunOutput)
    assert conclusion == CheckRunConclusion.ACTION_REQUIRED
    assert "JSON Schema validation found 3 issues" == output.title
    assert "The JSON schema validation found issues in JSON/YAML files." == output.summary
    assert len(output.annotations) == 3
    for annotation in output.annotations:
        assert annotation.annotation_level == AnnotationLevel.WARNING
        assert annotation.path
        assert annotation.message
        assert annotation.title
    
    assert set(
        (a.start_line, a.end_line, a.start_column, a.end_column)
        for a in output.annotations
    ) == {
        (1, 1, 1, 1),
        (4, 4, 4, 19),
        (6, 6, 4, 18)
    }