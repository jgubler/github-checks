"""Provides an interface to run the checks directly, without any proxy Python code."""

import logging
import os
import pickle
import sys
from collections.abc import Callable, Iterable
from pathlib import Path

from configargparse import ArgumentParser

from github_checks.formatters.ruff import format_ruff_json_output
from github_checks.github_api import GitHubChecks
from github_checks.models import CheckRunConclusion, ChecksAnnotation

log_to_annotation_formatters: dict[
    str,
    Callable[[Path, Path], Iterable[ChecksAnnotation]],
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
        help="File in which the authenticated checks session will be cached.",
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
        "orchestration actions. This will store an authenticated GitHub checks session"
        "in the file configured in `--pickle-filepath`.",
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
    init_parser.add_argument(
        "--overwrite-existing",
        action="store_true",
        help="If an existing checks session is found (pickle file exists), overwrite it"
        ". If a session is found and this is not set, initialization will abort.",
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
    gh_checks: GitHubChecks

    if args.command == "init":
        os.environ["GH_REPO_BASE_URL"] = args.repo_base_url

        if args.pickle_filepath.exists() and not args.overwrite_existing:
            logging.fatal(
                "[github-checks] Trying to initialize GitHub checks, but an instance "
                "is already initialized (pickle file exists) and `--overwrite-existing`"
                " is not set. Aborting.",
            )
            sys.exit(-1)

        gh_checks = GitHubChecks(
            repo_base_url=args.repo_base_url,
            app_id=args.app_id,
            app_installation_id=args.app_install_id,
            app_privkey_pem=args.pem_path,
        )
        with args.pickle_filepath.open("wb") as pickle_file:
            pickle.dump(gh_checks, pickle_file)

    if args.command == "start-check-run":
        if not args.pickle_filepath.exists():
            logging.fatal(
                "[github-checks] Trying to start a github check without "
                "initialization (pickle file not found). Aborting.",
            )
            sys.exit(-1)
        with args.pickle_filepath.open("rb") as pickle_file:
            gh_checks = pickle.load(pickle_file)  # noqa: S301
        gh_checks.start_check_run(
            revision_sha=args.revision_sha,
            check_name=args.check_name,
        )
        with args.pickle_filepath.open("wb") as pickle_file:
            pickle.dump(gh_checks, pickle_file)

    elif args.command == "add-check-annotations":
        if not args.pickle_filepath.exists():
            logging.fatal(
                "[github-checks] Trying to update a github check, but no check "
                "is currently running. Aborting.",
            )
            sys.exit(-1)

        if not args.local_repo_path:
            # assume that local repo is named same as remote
            # try splitting repo URL for last part of path and appending to cwd
            remote_repo_name: str | None = os.getenv("GH_REPO_BASE_URL", None)
            if (
                not remote_repo_name
                or not (
                    local_repo_path := (Path().cwd() / remote_repo_name.split("/")[-1])
                )
                or not local_repo_path.exists()
            ):
                logging.fatal(
                    "[github-checks] Cannot find local repository copy for resolution "
                    "of relative paths. Aborting.",
                )
                sys.exit("-1")

        annotations = log_to_annotation_formatters[args.log_format](
            args.validation_log,
            Path(args.local_repo_path),
        )

        with args.pickle_filepath.open("rb") as pickle_file:
            gh_checks = pickle.load(pickle_file)  # noqa: S301
        gh_checks.update_annotations(list(annotations))

    elif args.command == "finish-check-run":
        if not args.pickle_filepath.exists():
            logging.fatal(
                "[github-checks] Error: Trying to update a github check, but no check "
                "is currently running. Quitting.",
            )
            sys.exit(-1)

        with args.pickle_filepath.open("rb") as pickle_file:
            gh_checks = pickle.load(pickle_file)  # noqa: S301
        gh_checks.finish_check_run(args.conclusion)

        # delete the pickle file for this run, it won't be needed anymore
        args.pickle_filepath.unlink()

        # unless disabled, clean up local environment variables
        if not args.no_cleanup:
            for env_var in [
                "GH_APP_ID",
                "GH_APP_INSTALL_ID",
                "GH_PRIVATE_KEY_PEM",
                "GH_REPO_BASE_URL",
                "GH_CHECK_REVISION",
                "GH_CHECK_NAME",
            ]:
                os.environ.pop(env_var, default=None)
