#!/bin/bash

# set up environment variables up front
export GH_APP_ID="1065841" GH_APP_INSTALL_ID="57443831"
export GH_PRIVATE_KEY_PEM="/home/jgubler-wsl/.ssh/demo-github-checks-app.pem"
export GH_REPO_BASE_URL="https://github.com/jgubler/github-checks"
export GH_CHECK_REVISION="$(git rev-parse HEAD)"
export GH_LOCAL_REPO_PATH="/home/jgubler-wsl/repos/github-checks"

# set up a venv, and install this package in it, including dev dependencies
# ideally we'll split CI dependencies from dev dependencies at some point
python3 -m venv .temp_venv
. .temp_venv/bin/activate
python3 -m pip install -e .[dev]

# initialize & start a check run
python3 -m github_checks.cli init --overwrite-existing
python3 -m github_checks.cli start-check-run --check-name ruff-checks

# run ruff on ourselves and pass its error messages as annotations to GitHub
ruff check . --output-format=json > ruff_output.json
python3 -m github_checks.cli add-check-annotations ruff_output.json --log-format ruff-json

# finish the check run and clean up the venv
python3 -m github_checks.cli finish-check-run
deactivate
rm -rf .temp_venv
