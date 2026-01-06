# type: ignore  # noqa: PGH003
# ruff: noqa: S101, D103, D100, INP001, ANN001
import pytest

from github_checks.cli import (
    compute_ignored_globs,
)


@pytest.mark.parametrize(
    ("ignored_globs", "included_globs", "ignore_except_included", "expected"),
    [
        (None, None, False, None),
        (["*.pyc", "*.log"], None, False, ["*.pyc", "*.log"]),
        (["*.pyc", "*.log"], ["src/*.py"], False, ["*.pyc", "*.log", "!src/*.py"]),
        (None, ["src/*.py"], True, ["!src/*.py"]),
        (["*.pyc", "*.log"], ["src/*.py"], True, ["!src/*.py"]),
        (None, None, True, None),
    ],
)
def test_compute_ignored_globs(
    ignored_globs,
    included_globs,
    ignore_except_included,
    expected,
) -> None:
    result = compute_ignored_globs(
        ignored_globs=ignored_globs,
        included_globs=included_globs,
        ignore_except_included=ignore_except_included,
    )
    assert result == expected
