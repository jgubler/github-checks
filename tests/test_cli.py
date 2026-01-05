import pytest  # noqa: D100, INP001

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
)  # type: ignore[misc]
def test_compute_ignored_globs(  # type: ignore[no-untyped-def] # noqa: D103
    ignored_globs,  # noqa: ANN001
    included_globs,  # noqa: ANN001
    ignore_except_included,  # noqa: ANN001
    expected,  # noqa: ANN001
) -> None:
    result = compute_ignored_globs(
        ignored_globs=ignored_globs,
        included_globs=included_globs,
        ignore_except_included=ignore_except_included,
    )
    assert result == expected  # noqa: S101
