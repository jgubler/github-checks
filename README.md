# github-checks
Minimal Python API for GitHub Checks to submit feedback from builds running on 3rd party build platforms.
Allows keeping individual CI code minimal in each repository, and is agnostic towards the build platform (GCP, Azure, Actions, etc.) being used.

> [!IMPORTANT]
> Still under initial development, not intended for use in production CI yet.

## Prerequisites

1. You have a code repository that you want to validate, which is hosted on either GitHub Cloud or GitHub Enterprise
2. You have created a GitHub App in your global GitHub user profile (in case of personal use), or in your organization user's profile
3. The "locally" wherever that may be accessible private key PEM file, as provided to you by GitHub for your App
4. The GitHub app in (2) has been "installed" to the GitHub repository in (1)

In the usage below, you will need the repository URL, the App ID, the App installation ID and the PEM file.

## Usage

There's two usage options, as a library and directly via CLI. Using the package as a library in your Python code gives you full flexibility, while the CLI option may allow you to keep your CI absolutely minimal.

To alleviate the burden of manually formatting annotations from validation logs, pre-built formatters are provided in `github_checks.formatters`.
Note that for CLI usage, a supported validation log format is necessary, as annotations cannot be manually formatted in this mode.
At the moment, only Ruff's JSON output is supported, however more are planned (mypy, SARIF, etc.).

### CLI
See [tests/run_checks_on_ourselves.sh](tests/run_checks_on_ourselves.sh) for an example, which uses the CLI to validate this repository.

### As a library

```python
app_token: str = authenticate_as_github_app(
    app_id=YOUR_APP_ID,
    app_installation_id=YOUR_APP_INSTALLATION_ID,
    app_privkey_pem=Path("/path/to/privkey.pem"),
)

check_run: CheckRun = CheckRun(
    repo_base_url=YOUR_REPO_BASE_URL,  # e.g. https://github.com/yourname/yourrepo
    revision_sha=HASH_OF_COMMIT_TO_BE_CHECKED,
    check_name="SomeCheck",
    app_access_token=app_token,
)

validation_results = your_local_validation_function()
annotations = []
for result in validation_results:
    annotations.append(
        ChecksAnnotation(
            title="SomeCheck doesn't like this code",
            annotation_level=AnnotationLevel.FAILURE,
            start_line=result.start_line,
            start_column=result.start_column,
            end_line=result.end_line,
            end_column=result.end_column,
            filepath=result.repo_relative_filepath,
            message=result.validation_issue_msg,
            raw_details=str(result),
        )
    )

check_run.update_annotations(annotations)
check_run.finish()
```
