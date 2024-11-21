"""Provides an interface to run the checks directly, without any proxy Python code."""

import logging
import os
import pickle
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from urllib.parse import ParseResult, urlparse

from configargparse import ArgumentParser

from github_checks.formatters.ruff import format_ruff_json_output
from github_checks.github_api import CheckRun, authenticate_as_github_app
from github_checks.models import CheckRunConclusion, ChecksAnnotation

log_to_annotation_formatters: dict[
    str,
    Callable[[str, Path], Iterable[ChecksAnnotation]],
] = {
    "ruff-json": format_ruff_json_output,
}


if __name__ == "__main__":
    argparser = ArgumentParser(
        prog="github-checks",
        description="CLI for the github-checks library. Please note: the commands of "
        "this CLI need to be used in a specific order (see individual command help for "
        "details) and pass values to each other through environment variables.",
    )
    argparser.add_argument(
        "--pickle-filepath",
        type=Path,
        default=Path("/tmp/github-checks.pkl"),  # noqa: S108
        help="path for the file in which the check run state will be conserved",
    )
    subparsers = argparser.add_subparsers(
        description="Operation to be performed by the CLI.",
        required=True,
        dest="command",
    )
    init_parser = subparsers.add_parser(
        "init",
        help="Authenticate this environment as a valid check run session for the GitHub"
        " App installation, retrieving an app token to authorize subsequent check run "
        "orchestration actions. This will set a `GH_APP_TOKEN` environment variable.",
    )
    init_parser.add_argument(
        "--app-id",
        type=str,
        env_var="GH_APP_ID",
        help="ID of the GitHub App that is authorized to orchestrate Check Runs.",
    )
    init_parser.add_argument(
        "--pem-path",
        type=Path,
        env_var="GH_PRIVATE_KEY_PEM",
        help="Private key to authenticate as the GitHub App specified in --app-id.",
    )
    init_parser.add_argument(
        "--repo-base-url",
        type=str,
        env_var="GH_REPO_BASE_URL",
        help="Base URL of the repo with scheme, e.g. https://github.com/jdoe/myproject.",
    )
    init_parser.add_argument(
        "--app-install-id",
        type=str,
        env_var="GH_APP_INSTALL_ID",
        help="ID of the repository's GitHub App installation used by the check.",
    )

    start_parser = subparsers.add_parser(
        "start-check-run",
        help="Start a check run for a specific commit/revision hash, using the "
        "current initialized session. Will show up in GitHub PRs as a running check.",
    )
    start_parser.add_argument(
        "--revision-sha",
        type=str,
        env_var="GH_CHECK_REVISION",
        help="Revision/commit SHA hash that this check run is validating.",
    )
    start_parser.add_argument(
        "--check-name",
        type=str,
        env_var="GH_CHECK_NAME",
        help="A name for this check run. Will be shown on any respective GitHub PRs.",
    )

    annotation_parser = subparsers.add_parser(
        "add-check-annotations",
        help="Update an existing check run with annotations from local validation "
        "output. These will show up as comments on (where available) the specified "
        "lines of code in any pull requests with this commit.",
    )
    annotation_parser.add_argument(
        "validation_log",
        type=Path,
        help="Logfile of a supported format (see option --format for details).",
    )
    annotation_parser.add_argument(
        "--log-format",
        choices=log_to_annotation_formatters.keys(),
        required=True,
        help="Format of the provided log file.",
    )
    annotation_parser.add_argument(
        "--local-repo-path",
        type=Path,
        env_var="GH_LOCAL_REPO_PATH",
        required=False,
        help="Path to the local copy of the repository, for deduction of relative paths"
        " by the formatter, for any absolute paths contained in the logfile. If not "
        "provided, it will be assumed to be in the current working directory, under the"
        " same name as the remote GitHub repository. Throws an error if not.",
    )

    finish_parser = subparsers.add_parser(
        "finish-check-run",
        help="End the currently running check run, posting the appropriate conclusion.",
    )
    finish_parser.add_argument(
        "--conclusion",
        choices=CheckRunConclusion,
        required=False,
        help="Conclusion this check run should finish with, optional. If not provided, "
        "either success or failure will be used, depending on presence of annotations.",
    )
    finish_parser.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Don't clean up local environment variables. Note: Only use this if you "
        "plan to run another checks run in this environment. Otherwise, sensitive "
        "information is left on the local file system (e.g. access token), which can "
        "pose a security risk.",
    )

    args = argparser.parse_args(sys.argv[1:])

    if args.command == "init":
        os.environ["GH_REPO_BASE_URL"] = args.repo_base_url
        # we do need the repo base url later, but we only need domain itself here
        # for github cloud, this would be https://github.com, for enterprise it's diff
        url_parts: ParseResult = urlparse(args.repo_base_url)
        github_api_base_url: str = f"{url_parts.scheme}://api.{url_parts.netloc}"

        token = authenticate_as_github_app(
            app_id=args.app_id,
            app_installation_id=args.app_install_id,
            github_api_base_url=github_api_base_url,
            app_privkey_pem=args.pem_path,
        )
        os.environ["GH_APP_TOKEN"] = token

    check_run: CheckRun
    if args.command == "start-check-run":
        repo_base_url: str | None = os.getenv("GH_REPO_BASE_URL", None)
        github_app_token: str | None = os.getenv("GH_APP_TOKEN")
        if not (repo_base_url and github_app_token):
            sys.exit(
                "[github-checks] Error: Trying to start a github check without "
                "initialization. Quitting.",
            )
        check_run = CheckRun(
            repo_base_url=repo_base_url,
            revision_sha=args.revision_sha,
            check_name=args.check_name,
            app_access_token=github_app_token,
        )
        with args.pickle_filepath.open("wb") as pickle_file:
            pickle.dump(check_run, pickle_file)

    elif args.command == "add-check-annotations":
        if not args.pickle_filepath.exists():
            logging.fatal(
                "[github-checks] Error: Trying to update a github check, but no check "
                "is currently running. Quitting.",
            )
            sys.exit(-1)

        if not args.local_repo_path:
            # assume that local repo is named same as remote
            # try splitting repo URL for last part of path and appending to cwd
            remote_repo_name: str | None = os.getenv("GH_REPO_BASE_URL", None)
            if (
                not remote_repo_name
                or not (
                    local_repo_path := Path().cwd() / remote_repo_name.split("/")[-1]
                )
                or not local_repo_path.exists()
            ):
                logging.fatal(
                    "Cannot find local repository copy for resolution of relative "
                    "paths. Aborting.",
                )
                sys.exit("-1")

        annotations = log_to_annotation_formatters[args.log_format](
            args.validation_log,
            local_repo_path,
        )

        with args.pickle_filepath.open("rb") as pickle_file:
            check_run = pickle.load(pickle_file)  # noqa: S301
        check_run.update_annotations(list(annotations))

    elif args.command == "finish-check-run":
        if not args.pickle_filepath.exists():
            logging.fatal(
                "[github-checks] Error: Trying to update a github check, but no check "
                "is currently running. Quitting.",
            )
            sys.exit(-1)

        with args.pickle_filepath.open("rb") as pickle_file:
            check_run = pickle.load(pickle_file)  # noqa: S301
        check_run.finish(args.conclusion)

        # delete the pickle file for this run, it won't be needed anymore
        args.pickle_filepath.unlink()

        # unless disabled, clean up local environment variables
        if not args.no_cleanup:
            for env_var in [
                "GH_APP_TOKEN",
                "GH_APP_ID",
                "GH_APP_INSTALL_ID",
                "GH_PRIVATE_KEY_PEM",
                "GH_REPO_BASE_URL",
                "GH_CHECK_REVISION",
                "GH_CHECK_NAME",
            ]:
                os.environ.pop(env_var, default=None)
