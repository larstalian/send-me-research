#!/usr/bin/env bash

set -euo pipefail

CODEX_DIR="${HOME}/.codex"
AUTH_FILE="${CODEX_DIR}/auth.json"
CONFIG_FILE="${CODEX_DIR}/config.toml"

if [[ ! -f "${AUTH_FILE}" ]]; then
  echo "Missing ${AUTH_FILE}. Run 'codex login' first." >&2
  exit 1
fi

if [[ ! -f "${CONFIG_FILE}" ]]; then
  echo "Missing ${CONFIG_FILE}. Expected Codex config alongside auth." >&2
  exit 1
fi

base64_encode() {
  if base64 --help 2>/dev/null | grep -q -- '--wrap'; then
    base64 --wrap=0 "$1"
  else
    base64 < "$1" | tr -d '\n'
  fi
}

echo "Create these GitHub repository secrets:"
echo
echo "CODEX_AUTH_JSON_BASE64=$(base64_encode "${AUTH_FILE}")"
echo
echo "CODEX_CONFIG_TOML_BASE64=$(base64_encode "${CONFIG_FILE}")"
