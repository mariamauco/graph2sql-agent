#!/usr/bin/env bash
set -euo pipefail

# Resolve paths from this script so it can be launched from any directory.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
DOWNLOAD_DIR="${REPOSITORY_DIR}/data/spider_databases"

# The command is installed by huggingface_hub[cli] in the active virtualenv.
if ! command -v huggingface-cli >/dev/null 2>&1; then
    printf '%s\n' "huggingface-cli was not found. Activate the venv and install requirements first." >&2
    exit 1
fi

[ -d "$DOWNLOAD_DIR" ] || mkdir -p "$DOWNLOAD_DIR"

# Download the Spider databases and metadata from the public Hugging Face dataset.
huggingface-cli download \
    Chinastark/spider_datasets \
    --repo-type dataset \
    --local-dir "${DOWNLOAD_DIR}"

printf 'Spider dataset downloaded to %s\n' "${DOWNLOAD_DIR}"