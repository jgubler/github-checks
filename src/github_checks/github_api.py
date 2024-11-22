"""Utility functions to help interface with the GitHub checks API."""

import json
import logging
import sys
import time
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import ParseResult, urlparse

import jwt
from requests import HTTPError, Response, Session

from github_checks.models import (
    AnnotationLevel,
    CheckAnnotation,
    CheckRunConclusion,
    CheckRunOutput,
    CheckRunUpdatePOSTBody,
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
            jwt.jwk_from_pem(priv_key),
            alg="RS256",
        ),
    )


def _authenticate_as_github_app(  # noqa: PLR0913
    app_id: str,
    app_installation_id: str,
    app_privkey_pem: Path,
    github_session: Session,
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
    response: Response = github_session.post(url, headers=headers, timeout=timeout)
    try:
        response.raise_for_status()
    except HTTPError:
        logging.exception(str(response.text))
        sys.exit(-1)
    return str(response.json().get("token"))


def _delete_keys_from_nested_dict(dictionary: dict[str, Any]) -> None:
    for key in list(dictionary.keys()):
        if dictionary[key] is None:
            del dictionary[key]
        elif type(dictionary[key]) is dict:
            _delete_keys_from_nested_dict(dictionary[key])


class GitHubChecks:
    """Handler to start, update & finish Check runs for a GitHub repo."""

    repo_base_url: str
    app_id: str
    app_installation_id: str
    app_privkey_pem: Path
    gh_api_timeout: int
    current_run_id: str | None = None
    _api_headers: dict[str, str]
    _curr_check_name: str
    _curr_annotation_levels: set[AnnotationLevel]
    _curr_annotations_ctr: int
    _github_session: Session

    def __init__(
        self,
        repo_base_url: str,
        app_id: str,
        app_installation_id: str,
        app_privkey_pem: Path,
        gh_api_timeout: int = 10,
    ) -> None:
        """Initialize the headers for usage with the Checks API.

        :param repo_base_url: the base URL of the repository to run a check for
        :param app_id: ID of your app, e.g. found in the URL path of your App config
        :param app_installation_id: ID of the App's installation to the repo
        :param app_privkey_pem: private key provided by GitHub for this app, PEM format
        :param gh_api_timeout: API request timeout in seconds, optional, defaults to 10
        """
        # we do need the repo base url later, but we only need domain itself here
        # for github cloud, this would be https://github.com, for enterprise it's diff
        url_parts: ParseResult = urlparse(repo_base_url)
        github_api_base_url: str = f"{url_parts.scheme}://api.{url_parts.netloc}"
        self._github_session = Session()

        app_access_token = _authenticate_as_github_app(
            app_id,
            app_installation_id,
            app_privkey_pem,
            self._github_session,
            github_api_base_url,
        )
        self.repo_base_url = (
            f"{url_parts.scheme}://api.{url_parts.netloc}/repos{url_parts.path}"
        )
        self._api_headers: dict[str, str] = _get_jwt_headers(
            app_access_token,
            "application/vnd.github+json",
        )
        self.gh_api_timeout = gh_api_timeout

    def start_check_run(
        self,
        revision_sha: str,
        check_name: str,
    ) -> None:
        """Start a run of this check.

        :param revision_sha: the sha revision being evaluated by this check run
        :param check_name: the name to be used for this specific check
        :raises HTTPError: in case the GitHub API could not start the check run
        """
        json_payload: dict[str, str] = {
            "name": check_name,
            "head_sha": revision_sha,
            "status": "in_progress",
            "started_at": self._gen_github_timestamp(),
        }
        response: Response = self._github_session.post(
            f"{self.repo_base_url}/check-runs",
            json=json_payload,
            headers=self._api_headers,
            timeout=self.gh_api_timeout,
        )
        try:
            response.raise_for_status()
        except HTTPError:
            logging.fatal(
                "GitHub API responded with error code while attempting to start check"
                " run: %d - %s",
                response.status_code,
                response.text,
            )
            logging.warning(
                "This can occur due to incorrect URLs, please double check "
                "that %s is the correct API endpoint.",
                self.repo_base_url + "/check-runs",
            )
            return

        self._curr_check_name = check_name
        self.current_run_id = str(response.json().get("id"))
        self._curr_annotation_levels = set()
        self._curr_annotations_ctr = 0

    def finish_check_run(
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
        if not self.current_run_id:
            logging.fatal(
                "[github-checks] Trying to finish check run, but no check is running.",
            )
            return

        if not output:
            # set a minimal output, in case e.g. only a conclusion was passed
            output = CheckRunOutput(
                title=self._curr_check_name,
                summary=f"Check {self._curr_check_name} completed, "
                f"found {self._curr_annotations_ctr} issues.",
            )

        if not conclusion:
            if output.annotations:
                conclusion = self._infer_conclusion(output.annotations)
            else:
                conclusion = CheckRunConclusion.NEUTRAL

        if not output.annotations:
            self._post_check_run_update(output, conclusion)
        else:
            for annotations_chunk in self._annotation_batches(output.annotations):
                output.annotations = annotations_chunk
                self._post_check_run_update(output, conclusion)

        self.current_run_id = None

    def _post_check_run_update(
        self,
        output: CheckRunOutput,
        conclusion: CheckRunConclusion,
    ) -> None:
        json_payload: CheckRunUpdatePOSTBody = CheckRunUpdatePOSTBody(
            name=self._curr_check_name,
            completed_at=self._gen_github_timestamp(),
            output=output,
            conclusion=conclusion.value,
        )

        # Get rid of any null values, as they cause HTTP Status 422 errors at the API
        post_body_json = json_payload.model_dump_json(
            exclude_unset=True,
            exclude_none=True,
        )
        post_body_dict = json.loads(post_body_json)
        _delete_keys_from_nested_dict(post_body_dict)

        response: Response = self._github_session.patch(
            f"{self.repo_base_url}/check-runs/{self.current_run_id}",
            json=post_body_dict,
            headers=self._api_headers,
            timeout=self.gh_api_timeout,
        )
        response.raise_for_status()

    @staticmethod
    def _annotation_batches(
        annotations: list[CheckAnnotation],
        batch_size: int = 50,
    ) -> Iterable[list[CheckAnnotation]]:
        """Chunk the annotations, as GitHub API accepts <= 50 annotations at once."""
        for i in range(0, len(annotations), batch_size):
            yield annotations[i : i + batch_size]

    def _infer_conclusion(
        self,
        annotations: list[CheckAnnotation],
    ) -> CheckRunConclusion:
        annotation_levels = {annotation.annotation_level for annotation in annotations}
        if AnnotationLevel.FAILURE in annotation_levels:
            return CheckRunConclusion.ACTION_REQUIRED
        # both warning and notice should not block a pull request, but just inform
        return CheckRunConclusion.SUCCESS

    def _gen_github_timestamp(self) -> str:
        """Generate a timestamp for the current moment in the GitHub-expected format."""
        return (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
