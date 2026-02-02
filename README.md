# github-checks

![PyPI - Versions](https://img.shields.io/pypi/v/github-checks.svg)
![PyPI - License](https://img.shields.io/pypi/l/github-checks.svg)
![PyPI - Python Versions](https://img.shields.io/pypi/pyversions/ruff.svg)

Python API library for annotating GitHub pull requests with the results of quality check tools. Ensure quality centrally through what is essentially server-side pre-commit, catching client-side misconfigurations and bypasses.

## Quick Start

Using the Python type checker MyPy as an example, the following code is all you need to yield the results displayed below:

```bash
pip install mypy github-checks
python3 -m github_checks.cli init \
    --app-id $app_id --app-install-id $install_id \
    --pem-path /path/to/priv/key.pem \
    --repo-base-url https://github.com/jdoe/myrepo

python3 -m github_checks.cli start-check-run \
    --check-name mypy-checks --revision $sha
mypy . --output=json > mypy_output.json
python3 -m github_checks.cli finish-check-run mypy_output.json \
    --log-format mypy-json \
    --local-repo-path /path/to/repo
```

If you want to just see how this looks in practice within the format of a build pipeline YAML, have a look at the cloudbuild.yaml in this repository as an example, which does exactly that for this repository, to run in Google CloudBuild.

## Purpose: Annotating your pull requests with rich feedback from check tools

The core use case for this library is to annotate GitHub pull requests with the findings of any and all quality checkers for the repository, and where possible to provide detailed on-line-of-code issue comments as reported by common linters and type checkers, all with minimum CLI code as this library handles all the plumbing and formatting, and agnostic to whichever build/CI platform (GCP, Azure, GH Actions, Jenkins, etc.) is being used.

Uploading a check result status with a markdown-enabled summary is supported regardless of the tool producing it, enabling the use of this library for both less common third party tooling, as well as bespoke internal quality checkers. Beyond this, the CLI provides full built-in support of SARIF (the OASIS' standard for scan results) and the native JSON output formats of several widely used python tools (currently mypy, pyright, ruff, more planned) to provide on-line-of-code findings. Some non-Python tooling (e.g. check-jsonschema) is supported as well. See below for details on supported formats. Note that technically, we are annotating a commit revision, not a PR. In 99% of cases, this doesn't really matter, but it does e.g. mean that if you view a PR at different revision states, the checks will correspond.

Other use cases include using the library's GitHub auth capability by itself (which can be used to retrieve an auth token for the associated GitHub app, to perform arbitrary actions as such, e.g. to clone the repository in the first place), as well as usage as a python library, as all CLI functionality is also available to be used by other python code. However, the goal remains to only require 2-3 lines of shell code to instrument the CLI for any given check, which is much less overhead than direct python usage.

## Prerequisites

1. You have a code repository that you want to validate, which is hosted on either GitHub Cloud or GitHub Enterprise (on-premise / private cloud).
2. You have created a GitHub App in your global GitHub user profile (in case of personal use), or in your organization user's profile.
3. Your GitHub app has read access to this repository, and read and write access to its Checks API. See GitHub's docs for details on this.
4. You have configured your GitHub app to trigger a build in your build/CI platform of choice (GCP, Azure, AWS, GitHub actions, Jenkins, CircleCI, etc.), e.g. via an authenticated webhook. See "Initiating your build to run checks for a GitHub PR" below.
5. The build environment has access to the private key PEM file (in pkcs8 format for git's SSH connection) that you have created for your GitHub app.

Once you're running the checks, you'll need to provide the following information:

* The base GitHub URL of the repository
* The ID of the GitHub App, as well as the installation ID (which is specific to the app's installation in your repository/organization)
* The private key for the App, with which it can both pull the repository (acting as a deploy key) as well as authenticate as the App
* The path to your local copy of the repository (to allow the formatter to resolve relative filepaths in check output)
* And finally, the commit revision that your check is running against (so that the right commit hashes are being annotated with the results)

All of these can be passed either via environment variables or cmdline parameters, as either option may be more convenient for you depending on your build setup. Support for a configuration file is not planned at the moment, for lack of clear benefit.

## Natively Supported Annotation Formatters via CLI

Firstly, all tools whether they're fully supported (yet) or not can be used with their output just passed to the `raw` formatter (with GitHub's markdown syntax supported), and manually setting a fitting check conclusion via the tool's exit code.  
However, much of the value of this library lies in being able to use the built-in formatters for commonly used QA tooling, to create PR annotations on the code itself, rather than just a markdown conclusion, which is why we'll try to build out this support over time.  There is no structured prioritization for the remaining roadmap, input is welcome, as are contributions.

| Python QA Tools  | Native JSON | SARIF | Flags                                  |
|------------------|:-----------:|:-----:|----------------------------------------|
| ruff             |     ✅      |   ✅  | `--output-format=json\|sarif`          |
| pylint           |     🕒      |   ❌  | `--output-format=json2`                |
| flake8           |     🕒*     | (✅*) | `--format=json\|sarif`                 |
| black            |     ❌      |   ❌  | `--diff --color` (with `--raw`)        |
| mypy             |     ✅      |   ✅  | `--output=json`                        |
| pyright          |     ✅      |   ❌  | `--outputjson`                         |
| pytest           |     🕒*     |   ❌  | `--json-report`                        |
| bandit           |     🕒      |  (✅) | `-f json\|sarif`                       |
| pip-audit        |     ❌*     |   ❌  | `-f markdown (--desc on)` (with `raw`) |
| vulture          |     ❌      |   ❌  |                                        |
| pyroma           |     ❌      |   ❌  |                                        |

| Other QA Tools   | Native JSON | SARIF | Flags                              |
|------------------|:-----------:|:-----:|------------------------------------|
| check-jsonschema |     ✅      |   ❌  | `-o json`                          |
| shellcheck       |     🕒      |   ❌  | `-o json1`                         |
| markdownlint     |     🕒*     |   ❌  | `markdownlint-cli2-formatter-json` |
| eslint           |     🕒      | (✅*) | `-f json\|@microsoft/sarif`        |

* ✅ supported (tool has support and we have verified our native/sarif formatter correctly translates it)
* ✅* supported, but requires a plugin to be installed for the tool
* (✅) tool has SARIF output support, we just haven't verified it truly works as intended with our formatter
* 🕒 tool-supported, but our formatter is not implemented yet
* 🕒* tool-supported via plugin, but our formatter is not implemented yet
* ❌ tool does not support this output format
* ❌* has a native JSON output format, but it does not give us the data required (i.e. file and line of the issue within the repository) to specifically annotate

## Initiating your build to run checks for a GitHub PR

GitHub apps have the ability to subscribe to event types of a repository, and trigger an authenticated webhook for each event.
To configure this for use with this library, you would subscribe the App to the "Check Suite" events, and configure the webhook URL.

On the build side when receiving the webhook, you would then ideally want to add a build trigger condition/filter which validates that the `"action"` key in the JSON body of the webhook request has a value of either `"requested"` or `"rerequested"`. This will allow you to use the `Re-Run Checks` functionality in the `Checks` tab of the GitHub PR if needed. Additionally, if your build system allows you to extract build-available variables out of the webhook payload, you can avoid hardcoding them in your builds.

Some build pipelines have plugins for GitHub, allowing you to configure a direct "pull request trigger" to run your repository builds, which then perform & upload the checks, however we do not recommend using this, as that will come at the expense of the integrated re-run functionality via the App.

## CLI filters: dealing with the reality of partially-clean repositories

In a perfect world, you would of course run all your checkers across every single file in your repository on every single PR. That's both just the naive and simple approach, but there is also value to doing so, such that a type checker like mypy might alert you to a type issue in one.py, even if that file hasn't changed, but a function it imports and uses from two.py has, and the two are now incompatible.

Reality is commonly different, you might introduce quality checks incrementally to an existing "dirty" (uncompliant) repository, or you want to be less strict in your tests than in your source code.

Most quality checkers (especially linters and type checkers) allow you to flexibly configure things accordingly, e.g. ignoring certain files entirely or ignoring certain error codes for certain files/blocks/lines of code. It is reccommended to use those first wherever possible, as they will align across the IDE integrations, pre-commit checks and this library's usage.

However, for any fully supported input format, where this library is able to parse individual issues to build annotations, there are two command line flags of relevance with which you can filter through this library as well:

* `--ignored-globs-filepath` for use with a .gitignore-like file.
* `--included-globs-filepath` for use with git diff output, for files that should _always_ be included.
* `--ignore-except-included` whether to ignore everything that is not explicitly included.
* `--mute-ignored-annotations` whether to not just disregard filtered annotations for conclusion calculation, but to silence them entirely.

### Authenticating other GitHub actions using the GitHub App's access token

Depending on the permissions you've given to your app, you can also use its access token to perform other actions.
This might allow you to avoid managing additional deploy keys (which can only be scoped to individual repos).

For example, while some build environments generally provide you with a local copy of the repository that your build wants to process, this may not be available in some cases. Advanced multi-repo users might consider using this library to implement an organization-wide check app & build, which dynamically determines the to-be-validated repository based on the webhook parameters (more documentation on that to come). In
such a case, if your app has permissions to read contents of the respective repository you can use the access token as follows to clone:

```bash
git clone https://git:$TOKEN@github.com/$owner/$repo.git
```

To obtain the app token for this usage, you can instruct this lib's `init` command to return the bare token to you on stdout by passing the `--print-gh-app-install-token` flag. How you can pass this value to the git command depends on your build environment, as some may not allow executing python and git commands in the same step. In such cases, you'll want to pass the value through either an environment variable or file, depending on which option is feasible in your build environment (e.g. in Google CloudBuild, only files persists between steps).

## Using github-checks as a library

The following example showcases exemplary direct python usage:

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

## Roadmap: Future Work

In rough order of prioritization for the moment:

* Add build automation, which builds the wheel on each pushed commit, publishes a pre-release to PyPI for new master commits, and publishes a new stable release on a new tag. Currently this is all done locally.
* Add further native CLI formatter support
* Add a build status badge for the CI, using a cloud function triggered by the pubsub event of CloudBuild failure/success
* Add a tests status badge, reporting tests success of current master
* Migrate check run management persistence from pickling to JSON+pydantic (de-)serialization
  * The only reason for this lib to start out with using pickling was just slightly more convenience. Unpickling is generally considered risky with untrusted data (see e.g. the `suspicious-pickle-usage (S301)` warning by flake8-bandit), however there is a fairly high amount of trust in data in our case, therefore I did not see an issue with this. Nevertheless, it might be cleaner to handle it with JSON deserialization passed through pydantic instead, which is stricter/safer.
* Make check run management actually parallelizable & more flexible by maturing the persistence mechanism to be database-based
  * At the moment, check run management sort of works like a single-thread state machine:
    * `[Start] -init-> [Initialized]`
    * `[Initialized] -start-check-run-> [Running]`
    * `[Running] -finish-check-run-> [Initialized]`
    * `[Initialized] -cleanup-> [Start]`
  * State-relevant information is persisted unencrypted in a local `.pkl` pickle file that is read at start of each step and dumped again at its end.
  * While technically, we could manage the state of multiple check runs through this pickle file, this would obviously break down due to parallel access, needing a locking mechanism, at which point pickle is just no longer the right choice, and a database should be used instead. If we still want to manage things locally, sqlite should work well enough.

---

## Appendix: CLI usage

To allow viewing the full breadth of CLI options without installing the library, we provide the full CLI help outputs here, once for each available command:

```sh
❯ python3.11 src/github_checks/cli.py --help
usage: github-checks [-h] [--pickle-filepath PICKLE_FILEPATH] {init,start-check-run,finish-check-run,cleanup} ...

CLI for the github-checks library. Please note: the commands of this CLI need to be used in a specific order (see individual command help
for details) and pass values to each other through environment variables.

options:
  -h, --help            show this help message and exit
  --pickle-filepath PICKLE_FILEPATH
                        File in which the authenticated checks session will be cached. [env var: GH_PICKLE_FILEPATH]

subcommands:
  Operation to be performed by the CLI.

  {init,start-check-run,finish-check-run,cleanup}
    init                Authenticate this environment as a valid check run session for the GitHub App installation, retrieving an app token
                        to authorize subsequent check run orchestration actions. This will store an authenticated GitHub checks sessionin
                        the file configured in `--pickle-filepath`.
    start-check-run     Start a check run for a specific commit/revision hash, using the current initialized session. Will show up in GitHub
                        PRs as a running check.
    finish-check-run    Finish the currently running check run, posting all the check annotations, the surrounding summary output and the
                        appropriate check conclusion.
    cleanup             Clean up the local environment variables and the pickle file, if present. Recommended to use if you don't plan to
                        run another checks run in this environment. Otherwise, sensitive information is left on the local file system (e.g.
                        access token), which can pose a security risk.

 In general, command-line values override environment variables which override defaults.
```

```sh
❯ python3 src/github_checks/cli.py start-check-run --help
usage: github-checks start-check-run [-h] [--revision REVISION] [--check-name CHECK_NAME]

options:
  -h, --help            show this help message and exit
  --revision REVISION   Revision/commit SHA hash that this check run is validating. [env var: GH_CHECK_REVISION]
  --check-name CHECK_NAME
                        A name for this check run. Will be shown on any respective GitHub PRs. [env var: GH_CHECK_NAME]

 In general, command-line values override environment variables which override defaults.
```

```sh
❯ python3 src/github_checks/cli.py start-check-run --help
usage: github-checks start-check-run [-h] [--revision REVISION] [--check-name CHECK_NAME]

options:
  -h, --help            show this help message and exit
  --revision REVISION   Revision/commit SHA hash that this check run is validating. [env var: GH_CHECK_REVISION]
  --check-name CHECK_NAME
                        A name for this check run. Will be shown on any respective GitHub PRs. [env var: GH_CHECK_NAME]

 In general, command-line values override environment variables which override defaults.
```

```sh
❯ python3 src/github_checks/cli.py finish-check-run --help
usage: github-checks finish-check-run [-h] --log-format {check-jsonschema,ruff-json,mypy-json,pyright-json,sarif,raw} --local-repo-path
                                      LOCAL_REPO_PATH
                                      [--conclusion {action_required,success,failure,neutral,skipped,stale,timed_out,cancelled}]
                                      [--ignored-globs-filepath IGNORED_GLOBS_FILEPATH] [--included-globs-filepath INCLUDED_GLOBS_FILEPATH]
                                      [--ignore-except-included] [--mute-ignored-annotations]
                                      validation_log

positional arguments:
  validation_log        Logfile of a supported format (see option --format for details).

options:
  -h, --help            show this help message and exit
  --log-format {check-jsonschema,ruff-json,mypy-json,pyright-json,sarif,raw}
                        Format of the provided log file.
  --local-repo-path LOCAL_REPO_PATH
                        Path to the local copy of the repository, for deduction of relative paths by the formatter, for any absolute paths
                        contained in the logfile. [env var: GH_LOCAL_REPO_PATH]
  --conclusion {action_required,success,failure,neutral,skipped,stale,timed_out,cancelled}
                        Optional override for the conclusion this check run should finish with.If not provided, success/action_required are
                        used, depending on annotations.
  --ignored-globs-filepath IGNORED_GLOBS_FILEPATH, -i IGNORED_GLOBS_FILEPATH
                        File containing a list of file pattern globs to ignore for the check conclusion verdict. Note that annotations are
                        still published to GitHub for these files, just the conclusion calculation is affected. This can be useful to
                        incrementally introduce checks to an existing codebase, where some files are not yet fully compliant. Where
                        possible, use tool-specific exclusion listsinstead, via the tool's configuration options (e.g. via the respective
                        section in the pyproject.toml), as those will also be respected locally (e.g. in IDE linter integrations or pre-
                        commit hooks).
  --included-globs-filepath INCLUDED_GLOBS_FILEPATH
                        File containing a list of file pattern globs to explicitly include. Note that this overrides any ignores specified
                        in --ignored-globs-filepath. This can be useful to e.g. dump the result of `git diff <base_branch> --name-only` into
                        a file and pass it here, to include issues in any files changed in a pull request, even if a file is generally
                        excluded, thus encouraging contributors to refactor existing debt in drive-by mode.
  --ignore-except-included
                        If set, only files matching the globs in --included-globs-filepath will be considered for the check conclusion and
                        annotations. All other files will be ignored entirely. Can be useful to operate in a "diff-only validation" mode,
                        where only strictly the files changed in a PR are considered. Danger: This can lead to dismissal of failed
                        (unmodified) tests, or oversight of failed side-effects, such as breaking type validation elsewhere in the codebase.
                        Use with caution. Requires --included-globs-filepath to be set.
  --mute-ignored-annotations
                        If set, annotations for ignored files will not just be disregarded when calculating the check's conclusion, but they
                        will be filtered entirely prior to publishing, silencing them entirely.

 In general, command-line values override environment variables which override defaults.
```
