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

# initialize the checks app to auth with GitHub
python3 -m github_checks.cli init --overwrite-existing

# run ruff on ourselves
python3 -m github_checks.cli start-check-run --check-name ruff-checks
ruff check . --output-format=json > ruff_output.json
python3 -m github_checks.cli finish-check-run ruff_output.json --log-format ruff-json --no-cleanup

# run mypy on ourselves
python3 -m github_checks.cli start-check-run --check-name mypy-checks
mypy . --output=json > mypy_output.json
python3 -m github_checks.cli finish-check-run mypy_output.json --log-format mypy-json --no-cleanup

# random raw output to test the raw log format
python3 -m github_checks.cli start-check-run --check-name test-raw-checks
echo "I just don't like this code" > raw_output.json
python3 -m github_checks.cli finish-check-run raw_output.json --log-format raw --no-cleanup

# random raw output to test the raw log format
python3 -m github_checks.cli start-check-run --check-name test-jsonschema-checks
check-jsonschema -o json --schemafile tests/json_validation/user.schema.json tests/json_validation/invalid_user.json > jsonschema_output.json
python3 -m github_checks.cli finish-check-run jsonschema_output.json --log-format check-jsonschema

# clean up the venv
deactivate
rm -rf .temp_venv
