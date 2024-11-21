"""Utility functions to help interface with the GitHub checks API."""

import logging
import sys
import time
from collections.abc import Iterable
from datetime import datetime
from itertools import islice
from pathlib import Path

import jwt
from requests import HTTPError, Response, patch, post

from github_checks.models import (
    AnnotationLevel,
    CheckRunConclusion,
    CheckRunOutput,
    CheckRunUpdatePOSTBody,
    ChecksAnnotation,
)


def _get_jwt_headers(jwt_str: str, accept_type: str) -> dict[str, str]:
    return {
        "Accept": f"{accept_type}",
        "Authorization": f"Bearer {jwt_str}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _generate_app_jwt_from_pem(
    pem_filepath: Path,
    app_id: str,
    ttl_seconds: int = 600,
) -> str:
    with pem_filepath.open("rb") as pem_file:
        priv_key = pem_file.read()
    jwt_payload = {
        "iat": int(time.time()),
        "exp": int(time.time()) + ttl_seconds,
        "iss": app_id,
    }
    return str(
        jwt.JWT().encode(
            jwt_payload,
            jwt.jwk_from_pem(priv_key.strip()),
            alg="RS256",
        ),
    )


def authenticate_as_github_app(
    app_id: str,
    app_installation_id: str,
    app_privkey_pem: Path,
    github_api_base_url: str = "https://api.github.com",
    timeout: int = 10,
) -> str:
    """Authenticate as the specified GitHub App installation to get an access token.

    :param app_id: ID of your app, e.g. found in the URL path of your App config
    :param app_installation_id: ID of the App's installation to the repo
    :param app_privkey_pem: private key provided by GitHub for this app, in PEM format
    :param github_api_base_url: API URL of your GitHub instance (cloud or enterprise)
    :param timeout: request timeout in seconds, optional, defaults to 10
    :return: the GitHub App access token
    """
    app_jwt: str = _generate_app_jwt_from_pem(app_privkey_pem, app_id)
    url: str = (
        f"{github_api_base_url}/app/installations/{app_installation_id}/access_tokens"
    )
    headers = _get_jwt_headers(
        app_jwt,
        "application/vnd.github+json",
    )
    response: Response = post(url, headers, timeout=timeout)
    try:
        response.raise_for_status()
    except HTTPError:
        logging.exception(str(response.text))
        sys.exit(-1)
    return str(response.json().get("token"))


class CheckRun:
    """Handler to start, update & finish an individual GitHub Check run."""

    repo_base_url: str
    check_name: str
    app_access_token: str
    _annotation_levels: set[AnnotationLevel]
    _annotations_ctr: int = 0
    _current_run_id: str | None

    def __init__(
        self,
        repo_base_url: str,
        revision_sha: str,
        check_name: str,
        app_access_token: str,
        gh_api_timeout: int = 10,
    ) -> None:
        """Initialize the headers for usage with the Checks API.

        :param repo_base_url: the base URL of the repository to run a check for
        :param revision_sha: the sha revision being evaluated by this check run
        :param check_name: the name to be used for this specific check
        :param app_access_token: authenticated token of a GitHub app that can run checks
        :param gh_api_timeout: API request timeout in seconds, optional, defaults to 10
        """
        self.repo_base_url = repo_base_url
        self.revision_sha = revision_sha
        self.check_name = check_name
        self.headers: dict[str, str] = _get_jwt_headers(
            app_access_token,
            "application/vnd.github.antiope-preview+json",
        )
        self.gh_api_timeout = gh_api_timeout
        self.current_run_id = self._start()
        self._annotation_levels = set()

    def _gen_github_timestamp(self) -> str:
        """Generate a timestamp for the current moment in the GitHub-expected format."""
        return datetime.now().astimezone().replace(microsecond=0).isoformat()

    def _start(self) -> str:
        """Start a run of this check.

        :raises HTTPError: in case the GitHub API could not start the check run
        """
        json_payload: dict[str, str] = {
            "name": self.check_name,
            "head_sha": self.revision_sha,
            "status": "in_progress",
            "started_at": self._gen_github_timestamp(),
        }
        response: Response = post(
            f"{self.repo_base_url}/check_runs",
            json=json_payload,
            headers=self.headers,
            timeout=self.gh_api_timeout,
        )
        response.raise_for_status()
        return str(response.json().get("id"))

    def update_annotations(self, annotations: list[ChecksAnnotation]) -> None:
        """Update the current check run with a list of Checks annotations.

        :param annotations: the Checks annotations
        :raises HTTPError: in case the GitHub API could not start the check run
        """
        self._annotation_levels.update(
            annotation.annotation_level for annotation in annotations
        )
        self._annotations_ctr += len(annotations)

        for annotations_chunk in self._chunk_annotations_by_fifty(annotations):
            post_body: CheckRunUpdatePOSTBody = CheckRunUpdatePOSTBody(
                CheckRunOutput(
                    title=self.check_name,
                    summary=f"Check {self.check_name} completed, "
                    f"found {self._annotations_ctr} issues.",
                    annotations=annotations_chunk,
                ),
            )
            response: Response = patch(
                f"{self.repo_base_url}/check-runs/{self.current_run_id}",
                json=post_body.model_dump_json(exclude_unset=True),
                headers=self.headers,
                timeout=self.gh_api_timeout,
            )
            response.raise_for_status()

    @staticmethod
    def _chunk_annotations_by_fifty(
        annotations: Iterable[ChecksAnnotation],
    ) -> Iterable[list[ChecksAnnotation]]:
        """Chunk the annotations, as GitHub API accepts <= 50 annotations at once."""
        while True:
            if not (batch := islice(annotations, 50)):
                break
            yield list(batch)

    def finish(
        self,
        conclusion: CheckRunConclusion | None = None,
        output: CheckRunOutput | None = None,
    ) -> None:
        """Finish the currently running check run.

        If no conclusion is specified, `action_required` is chosen in case of any
        `failure`-level annotations, and `success` otherwise.

        :param output: the results of this check run, for annotating a PR, optional
        :param conclusion: the overall success, to be fed back for PR approval, optional
        :raises HTTPError: in case the GitHub API could not start the check run
        """
        if not output:
            output = CheckRunOutput(
                title=self.check_name,
                summary=f"Check {self.check_name} completed, "
                f"found {self._annotations_ctr} issues.",
            )
        if not conclusion:
            conclusion = (
                CheckRunConclusion.ACTION_REQUIRED
                if AnnotationLevel.FAILURE in self._annotation_levels
                else CheckRunConclusion.SUCCESS
            )
        json_payload: CheckRunUpdatePOSTBody = CheckRunUpdatePOSTBody(
            name=self.check_name,
            completed_at=self._gen_github_timestamp(),
            output=output,
            conclusion=conclusion.value,
        )
        response: Response = patch(
            f"{self.repo_base_url}/check-runs/{self.current_run_id}",
            json=json_payload.model_dump_json(exclude_unset=True),
            headers=self.headers,
            timeout=self.gh_api_timeout,
        )
        response.raise_for_status()
