#!/usr/bin/env bash

set -euo pipefail

REPO="${1:-${GITHUB_REPOSITORY:-}}"
AUTH_FILE="${CODEX_AUTH_FILE:-${HOME}/.codex/auth.json}"
CONFIG_FILE="${CODEX_CONFIG_FILE:-${HOME}/.codex/config.toml}"

if [[ -z "${GH_TOKEN:-}" ]]; then
  echo "Skipping Codex auth secret refresh because GH_TOKEN is not set."
  exit 0
fi

if [[ -z "${REPO}" ]]; then
  echo "Missing owner/repo. Pass it as the first argument or set GITHUB_REPOSITORY." >&2
  exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "Missing gh CLI." >&2
  exit 1
fi

if [[ ! -s "${AUTH_FILE}" ]]; then
  echo "Missing refreshed Codex auth file: ${AUTH_FILE}" >&2
  exit 1
fi

if [[ ! -s "${CONFIG_FILE}" ]]; then
  echo "Missing Codex config file: ${CONFIG_FILE}" >&2
  exit 1
fi

base64_encode() {
  if base64 --help 2>/dev/null | grep -q -- '--wrap'; then
    base64 --wrap=0 "$1"
  else
    base64 < "$1" | tr -d '\n'
  fi
}

gh secret set CODEX_AUTH_JSON_BASE64 --repo "${REPO}" < <(base64_encode "${AUTH_FILE}")
gh secret set CODEX_CONFIG_TOML_BASE64 --repo "${REPO}" < <(base64_encode "${CONFIG_FILE}")

echo "Refreshed hosted Codex auth secrets for ${REPO}."
