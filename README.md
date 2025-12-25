# github-checks
Minimal Python API for GitHub Checks to submit feedback from builds running on any build platform.
Allows keeping individual CI code minimal in each repository, and is agnostic towards the build platform (GCP, Azure, Actions, etc.) being used.

## Prerequisites

1. You have a code repository that you want to validate, which is hosted on either GitHub Cloud or GitHub Enterprise.
2. You have created a GitHub App in your global GitHub user profile (in case of personal use), or in your organization user's profile, which has read access to this repository, and read and write access to its Checks API.
3. The public key of your GitHub App has been added to the repository's deploy key, so the App can clone the repository during the CI build.
3. To authenticate during the CI build, the build environment must have access to the private key PEM file (in pkcs8 format for git's SSH connection).

Once you're running the checks, you'll need to provide the following information:
* The base GitHub URL of the repository
* The ID of the GitHub App, as well as the installation ID (which is specific to the app's installation in your repository/organization)
* The private key for the App, with which it can both pull the repository (acting as a deploy key) as well as authenticate as the App
* The path to your local copy of the repository (to resolve relative filepaths in check output)
* And finally, the commit revision that your check is running against (so that the right commit hashes are being annotated with the results)

These can be passed either via environment variables or cmdline parameters or, if using as a python library, via function parameters.

## Initiating your build to run checks for a GitHub PR 
GitHub apps have the ability to subscribe to event types of a repository, and trigger an authenticated webhook for each event.
To configure this for use with this library, you would subscribe the App to the "Check Suite" events, and configure the webhook URL.
On the build side when receiving the webhook, you would then want to add a build trigger condition/filter which validates that the `"action"` key in the JSON body of the webhook request has a value of either `"requested"` or `"rerequested"`. This will allow you to use the `Re-Run Checks` functionality in the `Checks` tab of the GitHub PR if needed.

Some build pipelines have plugins for GitHub, allowing you to configure a direct "pull request trigger" to run your repository builds, which then perform & upload the checks, however that will come at the expense of this integrated functionality via the App.

## Using github-checks in the build to upload results to the PR

There's two usage options, as a library and directly via CLI. In most cases, you will ususally want the CLI, as it comes with predefined formatters for annotations by common check tools, including support for the SARIF standard and the option to just paste a "raw" summary log if you don't want/need annotations.

If you want to mix the two approaches, you can also use the package as a library generally, and just import the pre-built formatters are provided in `github_checks.formatters` where they are available.

### CLI
If you want to just see how this looks in practice within the format of a build pipeline YAML, have a look at the cloudbuild.yaml in this repository as an example, which does exactly that for this repository, to run in Google CloudBuild.

However, putting build pipeline specifc syntax and setup of environment variables / cmdline parameters for GitHub App authentication aside, using the CLI is quite simple, as shown by this example running ruff checks:
```sh
python3 -m pip install github-checks ruff

# initialize the checks app to auth with GitHub, and let's ignore some dirty code
python3 -m github_checks.cli init --overwrite-existing
echo "/src/legacy_code/" > .checksignore

# start a check run (this will show a spinning check in the GitHub PR page)
python3 -m github_checks.cli start-check-run --check-name ruff-checks

ruff check . --output-format=json > ruff_output.json

# Finish the check run by providing ruff's output
# Let's ignore our legacy code for the check verdict, but still post annotations
python3 -m github_checks.cli finish-check-run ruff_output.json --log-format ruff-json --checksignore-filepath .checksignore --checksignore-verdict-only

# clean up, removing the GH_* environment variables and the pickle file cache
python3 -m github_checks.cli cleanup
```

#### Authenticating other GitHub actions using the GitHub Access Token
Depending on the permissions you've given to your app, you could of course also use its access token to perform other actions.
This might allow you to avoid managing additional deploy keys (which can only be scoped to individual repos).

For example, while some build environments generally provide you with a local copy of the repository that your build wants to process,
this may not be available in some cases. You could e.g. use this library to implement an organization-wide check app & build,
which dynamically determines the to-be-validated repository based on the webhook parameters (more documentation on that to come). In
such a case, if your app has permissions to read contents of the respective repository you can use the access token as follows to clone:

```bash
git clone https://git:$TOKEN@github.com/$owner/$repo.git
```

To obtain the app token for this usage, you can instruct this lib's `init` command to return the bare token to you on stdout by passing the `--print-gh-app-install-token` flag. How you can pass this value to the git command depends on your build environment, as some may not allow
executing python and git commands in the same step. In such cases, you'll want to pass the value through either an environment variable
or file, depending on which option is feasible in your build environment (e.g. in Google CloudBuild, only files persists between steps).

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

# Future Work

Add support for:
* pytest
* bandit
* pyroma
* vulture
* black
* shellcheck

Other features:
* Allow checks to run in parallel (likely using sqlite instead of a pickle file)
