# github-checks
Minimal Python API for GitHub Checks to submit feedback from builds running on any build platform.
Allows keeping individual CI code minimal in each repository, and is agnostic towards the build platform (GCP, Azure, Actions, etc.) being used.

## Prerequisites

1. You have a code repository that you want to validate, which is hosted on either GitHub Cloud or GitHub Enterprise
2. You have created a GitHub App in your global GitHub user profile (in case of personal use), or in your organization user's profile
3. The "locally" wherever that may be accessible private key PEM file, as provided to you by GitHub for your App
4. The GitHub app in (2) has been "installed" to the GitHub repository in (1), with permissions to the repository's Checks

In the usage below, you will need the repository URL, the App ID, the App installation ID and the PEM file.

## Usage

There's two usage options, as a library and directly via CLI. Using the package as a library in your Python code gives you full flexibility, while the CLI option may allow you to keep your CI absolutely minimal.

To alleviate the burden of manually formatting annotations from validation logs, pre-built formatters are provided in `github_checks.formatters`.
Note that for CLI usage, a supported validation log format is necessary, as annotations cannot be manually formatted in this mode.
At the moment, only Ruff's JSON output is supported, however more are planned (mypy, SARIF, etc.).

### CLI
See our shell script, which uses our own CLI to validate this repository with ruff:

https://github.com/jgubler/github-checks/blob/main/tests/run_checks_on_ourselves.sh#L1-L28

### As a library

```python

from github_checks.github_api import GitHubChecks
from github_checks.models import (
    AnnotationLevel,
    CheckAnnotation,
    CheckRunConclusion,
    CheckRunOutput,
)

gh_checks: GitHubChecks = GitHubChecks(
    repo_base_url=YOUR_REPO_BASE_URL,  # e.g. https://github.com/yourname/yourrepo
    app_id=YOUR_APP_ID,
    app_installation_id=YOUR_APP_INSTALLATION_ID,
    app_privkey_pem=Path("/path/to/privkey.pem"),
)

gh_checks.start_check_run(
    revision_sha=HASH_OF_COMMIT_TO_BE_CHECKED,
    check_name="SomeCheck",
)

check_run_output = CheckRunOutput(
    title="short",
    summary="longer",
    annotations=[
        CheckAnnotation(
            annotation_level=AnnotationLevel.WARNING,
            start_line=1,
            start_column=1,  # caution: only use columns when start_line==end_line!
            end_line=1,
            end_column=10,
            path="src/myfile.py",
            message="this is no bueno",
            raw_details="can't believe you've done this",
            title="[NO001] no-bueno",
        ),
        ...
    ]
)

gh_checks.finish_check_run(
    CheckRunConclusion.ACTION_REQUIRED,
    check_run_output,
)
```

## How to initiate the Checks
Depending on your build environment and if it has an integration with GitHub, you may be able to use a direct "pull request trigger" to run your builds, which then perform & upload the checks.
However, note that GitHub Apps can also be configured to trigger webhooks based on the events of the repository they're connected to. This may be useful, as this will e.g. also allow you to use the "Re-Run Checks" functionality in the GitHub PR web interface, which will then re-trigger that webhook.
