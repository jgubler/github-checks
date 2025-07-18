"""Utility functions for formatting and filtering GitHub check annotations."""

import os
from collections.abc import Generator, Iterable
from pathlib import Path

from pathspec import GitIgnoreSpec

from github_checks.models import AnnotationLevel, CheckAnnotation, CheckRunConclusion


def get_conclusion(annotations: Iterable[CheckAnnotation]) -> CheckRunConclusion:
    """Determine the conclusion based on the annotations."""
    # If any annotation is not a notice, we consider it an action required
    if any(
        annotation.annotation_level != AnnotationLevel.NOTICE
        for annotation in annotations
    ):
        return CheckRunConclusion.ACTION_REQUIRED

    return CheckRunConclusion.SUCCESS


def filter_for_checksignore(
    annotations: Iterable[CheckAnnotation],
    ignore_globs: list[str] | None,
    local_repo_base: Path,
) -> Generator[CheckAnnotation]:
    """Filter annotations based on ignore globs."""
    if not ignore_globs:
        yield from annotations
        return

    # Make sure we're in repo base, otherwise globs won't match correctly
    os.chdir(local_repo_base)
    ignore_matcher = GitIgnoreSpec.from_lines(ignore_globs)

    for annotation in annotations:
        # Check if the annotation path matches any of the ignore globs
        if not ignore_matcher.match_file(annotation.path):
            yield annotation
