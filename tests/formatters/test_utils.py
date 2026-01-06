# type: ignore  # noqa: PGH003
# ruff: noqa: S101, D103, D100, INP001

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from github_checks.formatters.utils import filter_for_checksignore, get_conclusion
from github_checks.models import AnnotationLevel, CheckAnnotation, CheckRunConclusion


@pytest.fixture
def annotations() -> list[CheckAnnotation]:
    return [
        CheckAnnotation(
            path="file1.py",
            start_line=1,
            end_line=1,
            annotation_level=AnnotationLevel.NOTICE,
            message="Notice message",
        ),
        CheckAnnotation(
            path="file2.py",
            start_line=2,
            end_line=2,
            annotation_level=AnnotationLevel.WARNING,
            message="Warning message",
        ),
    ]


def test_get_conclusion_success() -> None:
    annotations = [
        CheckAnnotation(
            path="file1.py",
            start_line=1,
            end_line=1,
            annotation_level=AnnotationLevel.NOTICE,
            message="Notice message",
        ),
    ]
    assert get_conclusion(annotations) == CheckRunConclusion.SUCCESS


def test_get_conclusion_action_required(annotations: list[CheckAnnotation]) -> None:
    assert get_conclusion(annotations) == CheckRunConclusion.ACTION_REQUIRED


def test_filter_for_checksignore_no_ignore_globs(
    annotations: list[CheckAnnotation],
) -> None:
    local_repo_base = Path("/fake/repo")
    result = list(filter_for_checksignore(annotations, None, local_repo_base))
    assert result == annotations


@patch("os.chdir")
def test_filter_for_checksignore_with_ignore_globs(
    mock_chdir,  # noqa: ANN001
    annotations: list[CheckAnnotation],
) -> None:
    ignore_globs = ["*.py"]
    local_repo_base = Path("/fake/repo")

    mock_ignore_matcher = MagicMock()
    mock_ignore_matcher.match_file.side_effect = lambda path: path.endswith(".py")

    with patch(
        "github_checks.formatters.utils.GitIgnoreSpec.from_lines",
        return_value=mock_ignore_matcher,
    ):
        result = list(
            filter_for_checksignore(annotations, ignore_globs, local_repo_base),
        )

    mock_chdir.assert_called_once_with(local_repo_base)
    assert result == []


@patch("os.chdir")
def test_filter_for_checksignore_with_ignore_globs_full(
    mock_chdir,  # noqa: ANN001
    annotations: list[CheckAnnotation],
) -> None:
    # check without mocking gitignorespec
    ignore_globs = ["file1.py"]
    local_repo_base = Path("/fake/repo")
    result = list(
        filter_for_checksignore(annotations, ignore_globs, local_repo_base),
    )
    mock_chdir.assert_called_once_with(local_repo_base)
    assert result == [annotations[1]]  # only file2.py remains
