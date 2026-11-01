#!/usr/bin/env bash
set -euo pipefail

# Run this once from a clean checkout to prepare and start development services.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "${REPOSITORY_DIR}"
DOWNLOAD_DIR="${REPOSITORY_DIR}/data/spider_databases"

# Create the virtual environment only when it does not already exist.
if [[ ! -d .venv ]]; then
    python3 -m venv .venv
fi

# Install the Python and Hugging Face CLI dependencies into the project venv.
source .venv/bin/activate
python3 -m pip install -r requirements.txt

# Download the Spider release before selecting a runtime database.
if [ -z "$(find "$DOWNLOAD_DIR" -mindepth 1 -maxdepth 1 -print -quit)" ]; then
    ./scripts/download_spider_data.sh
fi

# Build images and start the local Ollama profile in the background.
docker compose --profile ollama up --build -d