#!/usr/bin/env bash
set -euo pipefail

# Copy one Spider database to data/ so the agent discovers it at runtime.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
DB_NAME="${1:-}"

if [[ -z "${DB_NAME}" || ! "${DB_NAME}" =~ ^[A-Za-z0-9._-]+$ ]]; then
    printf 'Usage: %s <database-name>\n' "${0##*/}" >&2
    exit 2
fi

SOURCE="${REPOSITORY_DIR}/data/spider_databases/database/${DB_NAME}/${DB_NAME}.sqlite"
TARGET="${REPOSITORY_DIR}/data/${DB_NAME}.sqlite"

if [[ ! -f "${SOURCE}" ]]; then
    printf 'Spider database not found: %s\n' "${SOURCE}" >&2
    exit 1
fi

# Keep the downloaded release untouched and replace only the runtime copy.
cp "${SOURCE}" "${TARGET}"
printf 'Selected %s -> %s\n' "${DB_NAME}" "${TARGET}"