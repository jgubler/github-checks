"""Utility functions to help interface with the GitHub checks API."""

import time
from datetime import datetime
from pathlib import Path

import jwt
from requests import Response, patch, post

from models import CheckRunConclusion, CheckRunOutput


def _get_jwt_headers(jwt_str: str, accept_type: str) -> dict[str, str]:
    return {
        "Accept": f"{accept_type}",
        "Authorization": f"Bearer {jwt_str}",
    }


class AppInstallation:
    """Local installation of a GitHub app, identified by App ID and Installation ID."""

    app_id: str
    app_installation_id: str
    github_base_url: str

    def _generate_app_jwt_from_pem(
        self,
        pem_filepath: Path,
        ttl_seconds: int = 600,
    ) -> str:
        with pem_filepath.open("rb") as pem_file:
            priv_key = jwt.jwk_from_pem(pem_file.read())
        jwt_payload = {
            "iat": int(time.time()),
            "exp": int(time.time()) + ttl_seconds,
            "iss": self.app_id,
        }
        jwt_instance = jwt.JWT()
        return str(jwt_instance.encode(jwt_payload, priv_key, alg="RS256"))

    def authenticate(self, app_privkey_pem: Path, timeout: int = 10) -> str:
        """Authenticate this App installation with GitHub and get an access token.

        :param app_privkey_pem: private key for this app in PEM format
        :param timeout: request timeout in seconds, optional, defaults to 10
        :return: the GitHub App access token
        """
        app_jwt: str = self._generate_app_jwt_from_pem(app_privkey_pem)
        url: str = (
            f"{self.github_base_url}/app/installations/{self.app_installation_id}"
            "/access_tokens"
        )
        headers = _get_jwt_headers(
            app_jwt,
            "application/vnd.github.machine-man-preview+json",
        )
        response: Response = post(url, headers, timeout=timeout)
        response.raise_for_status()
        return str(response.json().get("token"))


class CodeRepoCheck:
    """Handler to start, utilize & finish an individual GitHub Checks run."""

    repo_base_url: str
    check_name: str
    checks_access_token: str
    current_run_id: str | None

    def __post_init__(self) -> None:
        """Initialize the headers for usage with the Checks API."""
        self.headers: dict[str, str] = _get_jwt_headers(
            self.checks_access_token,
            "application/vnd.github.antiope-preview+json",
        )

    def _gen_github_timestamp(self) -> str:
        """Generate a timestamp for the current moment in the GitHub-expected format."""
        return datetime.now().astimezone().replace(microsecond=0).isoformat()

    def start_check_run(self, revision_sha: str, timeout: int = 10) -> None:
        """Start a run of this check.

        :param revision_sha: the sha revision being evaluated by this check run
        :param timeout: request timeout in seconds, optional, defaults to 10
        :raises HTTPError: in case the GitHub API could not start the check run
        """
        json_payload: dict[str, str] = {
            "name": self.check_name,
            "head_sha": revision_sha,
            "status": "in_progress",
            "started_at": self._gen_github_timestamp(),
        }
        response: Response = post(
            f"{self.repo_base_url}/check_runs",
            json=json_payload,
            headers=self.headers,
            timeout=timeout,
        )
        response.raise_for_status()
        self.current_run_id = str(response.json().get("id"))

    def finish_check_run(
        self,
        output: CheckRunOutput,
        conclusion: CheckRunConclusion,
        timeout: int = 10,
    ) -> None:
        """Finish the currently running check run.

        :param output: the results of this check run, e.g. for annotating a PR
        :param conclusion: the overall success to be fed back, e.g. for PR approval
        """
        json_payload: dict[str, str | dict[str, str]] = {
            "name": self.check_name,
            "completed_at": self._gen_github_timestamp(),
            "output": output.model_dump(),
            "conclusion": conclusion.value,
        }
        response: Response = patch(
            f"{self.repo_base_url}/check-runs/{self.current_run_id}",
            json=json_payload,
            headers=self.headers,
            timeout=timeout,
        )
        response.raise_for_status()
