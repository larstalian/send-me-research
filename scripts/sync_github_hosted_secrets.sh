#!/usr/bin/env bash

set -euo pipefail

detect_repo() {
  if ! git remote get-url origin >/dev/null 2>&1; then
    return 1
  fi
  python - <<'PY'
from __future__ import annotations

import re
import subprocess

remote = subprocess.check_output(
    ["git", "remote", "get-url", "origin"],
    text=True,
).strip()
patterns = [
    r"github\.com[:/](?P<slug>[^/]+/[^/.]+)(?:\.git)?$",
    r"^git@github\.com:(?P<slug>[^/]+/[^.]+)(?:\.git)?$",
]
for pattern in patterns:
    match = re.search(pattern, remote)
    if match:
        print(match.group("slug"))
        raise SystemExit(0)
raise SystemExit(1)
PY
}

REPO="${1:-$(detect_repo || true)}"
CODEX_DIR="${HOME}/.codex"
AUTH_FILE="${CODEX_DIR}/auth.json"
CONFIG_FILE="${CODEX_DIR}/config.toml"
ENV_FILE="${2:-.env}"
PROFILES_FILE="${3:-digest_profiles.json}"

if [[ -z "${REPO}" ]]; then
  echo "Missing owner/repo. Pass it explicitly or set a GitHub origin remote first." >&2
  exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "Missing gh CLI." >&2
  exit 1
fi

if [[ ! -f "${AUTH_FILE}" || ! -f "${CONFIG_FILE}" ]]; then
  echo "Missing Codex auth files. Run 'codex login' first." >&2
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}. Expected mail settings there." >&2
  exit 1
fi

base64_encode() {
  if base64 --help 2>/dev/null | grep -q -- '--wrap'; then
    base64 --wrap=0 "$1"
  else
    base64 < "$1" | tr -d '\n'
  fi
}

set -a
source "${ENV_FILE}"
set +a

gh secret set CODEX_AUTH_JSON_BASE64 --repo "${REPO}" < <(base64_encode "${AUTH_FILE}")
gh secret set CODEX_CONFIG_TOML_BASE64 --repo "${REPO}" < <(base64_encode "${CONFIG_FILE}")

for key in EMAIL_TO EMAIL_FROM SMTP_HOST SMTP_PORT SMTP_USERNAME SMTP_PASSWORD OPENALEX_MAILTO; do
  value="${!key-}"
  if [[ -n "${value}" ]]; then
    gh secret set "${key}" --repo "${REPO}" < <(printf '%s' "${value}")
  fi
done

if [[ -n "${DIGEST_PROFILES_JSON:-}" ]]; then
  gh secret set DIGEST_PROFILES_JSON --repo "${REPO}" < <(printf '%s' "${DIGEST_PROFILES_JSON}")
elif [[ -f "${PROFILES_FILE}" ]]; then
  gh secret set DIGEST_PROFILES_JSON --repo "${REPO}" < "${PROFILES_FILE}"
fi

gh variable set DIGEST_AUTOMATION_MODE --repo "${REPO}" --body "hosted"

echo "Synced hosted workflow secrets for ${REPO}."
