"""Model representation of GitHub checks specific dictionary/json structures."""

from enum import Enum

from pydantic import BaseModel


class CheckRunConclusion(Enum):
    """The valid conclusion states of a check run."""

    SUCCESS = "success"
    ACTION_REQUIRED = "action_required"
    CANCELLED = "cancelled"


class AnnotationLevel(Enum):
    """The severity levels permitted by GitHub checks for each individual annotation."""

    NOTICE = "notice"
    WARNING = "warning"
    FAILURE = "failure"


class ChecksAnnotation(BaseModel):
    """Models the json expected by GitHub checks for each individual annotation."""

    repo_relative_filepath: str
    start_line: int | None
    end_line: int | None
    annotation_level: AnnotationLevel
    message: str
    raw_details: str | None


class CheckRunOutput(BaseModel):
    """The json format expected for the output of a Checks run."""

    title: str
    summary: str
    annotations: list[ChecksAnnotation] | None
