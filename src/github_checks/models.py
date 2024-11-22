"""Model representation of GitHub checks specific dictionary/json structures."""

from enum import Enum
from typing import Any

from pydantic import BaseModel


class CheckRunConclusion(Enum):
    """The valid conclusion states of a check run.

    See https://docs.github.com/en/rest/checks/runs#update-a-check-run for details.
    """

    ACTION_REQUIRED = "action_required"
    SUCCESS = "success"
    FAILURE = "failure"
    NEUTRAL = "neutral"
    SKIPPED = "skipped"
    STALE = "stale"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


class AnnotationLevel(Enum):
    """The severity levels permitted by GitHub checks for each individual annotation.

    See https://docs.github.com/en/rest/checks/runs#update-a-check-run for details.
    """

    NOTICE = "notice"
    WARNING = "warning"
    FAILURE = "failure"


class CheckRunAction(BaseModel):
    """Actions requested by this check run (never used in the context of this package).

    See https://docs.github.com/en/rest/checks/runs#update-a-check-run for details.
    """

    label: str
    description: str
    identifier: str


class ChecksImage(BaseModel):
    """Image posted on check run conclusion (never used in the context of this package).

    See https://docs.github.com/en/rest/checks/runs#update-a-check-run for details.
    """

    alt: str
    image_url: str
    caption: str | None


class CheckAnnotation(BaseModel):
    """Models the json expected by GitHub checks for each individual annotation.

    See https://docs.github.com/en/rest/checks/runs#update-a-check-run for details.
    """

    path: str
    message: str
    annotation_level: AnnotationLevel
    start_line: int = 0
    end_line: int = 0
    start_column: int | None = None  # note: only permitted on same line as end_column
    end_column: int | None = None  # note: only permitted on same line as start_column
    title: str | None = None
    raw_details: str | None = None

    def model_dump(  # noqa: D102
        self,
    ) -> Any:  # noqa: ANN401
        return super().model_dump(exclude_none=True, exclude_unset=True)


class CheckRunOutput(BaseModel):
    """The json format expected for the output of a Checks run.

    See https://docs.github.com/en/rest/checks/runs#update-a-check-run for details.
    """

    title: str | None
    summary: str
    text: str | None = None
    annotations: list[CheckAnnotation] | None = None
    images: list[ChecksImage] | None = None


class CheckRunUpdatePOSTBody(BaseModel):
    """The body for the POST request to be sent to `<repo_url>/check-runs/check_id_run`.

    See https://docs.github.com/en/rest/checks/runs#update-a-check-run for details.
    """

    name: str | None = None
    details_url: str | None = None
    external_id: str | None = None
    started_at: str | None = None
    status: str | None = None
    conclusion: str | None = None
    completed_at: str | None = None
    output: CheckRunOutput | None = None
    actions: CheckRunAction | None = None
