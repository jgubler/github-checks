#!/bin/bash

# set up environment variables up front
export GH_APP_ID="1065841" GH_APP_INSTALL_ID="57443831"
export GH_PRIVATE_KEY_PEM="<>"
export GH_REPO_BASE_URL="https://github.com/jgubler/github-checks"
export GH_CHECK_REVISION="$(git rev-parse HEAD)"
export GH_LOCAL_REPO_PATH="/Users/jgubler/repos/github-checks"

# set up a venv, and install this package in it, including dev dependencies
# ideally we'll split CI dependencies from dev dependencies at some point
python3 -m venv .temp_venv
. .temp_venv/bin/activate
python3 -m pip install -e .[dev]

# initialize & start a check run
python3 -m github_checks.cli init --overwrite-existing
python3 -m github_checks.cli start-check-run --check-name ruff-checks

# run ruff on ourselves
ruff check . --output-format=json > ruff_output.json

# finish the check run, passing ruff's errors as annotations to GitHub
python3 -m github_checks.cli finish-check-run ruff_output.json --log-format ruff-json --no-cleanup

python3 -m github_checks.cli start-check-run --check-name mypy-checks

# run mypy on ourselves
mypy . --output=json > mypy_output.json

# finish the check run, passing mypy's errors as annotations to GitHub
python3 -m github_checks.cli finish-check-run mypy_output.json --log-format mypy-json

# clean up the venv
deactivate
rm -rf .temp_venv
