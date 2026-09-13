#!/usr/bin/env bash
# Idempotent Cloud Agent install for the Bitcoin Data Collector.
# Creates an isolated virtualenv (project pins numpy<2, so it must not use a
# system numpy 2.x) and installs pinned dependencies. Safe to re-run.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# The venv module (ensurepip) must be present to create .venv. The environment
# snapshot normally already includes python3-venv; guard defensively so install
# still converges on a base image that lacks it.
if ! python3 -c "import ensurepip" >/dev/null 2>&1; then
  if command -v sudo >/dev/null 2>&1; then
    sudo apt-get update -qq
    sudo apt-get install -y -qq python3-venv
  fi
fi

# Create the venv if missing; reuse it otherwise (idempotent).
if [ ! -x ".venv/bin/python" ]; then
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
. .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt

echo "Bitcoin Data Collector environment ready. Activate with: source .venv/bin/activate"
