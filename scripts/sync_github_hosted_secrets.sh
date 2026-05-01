#!/usr/bin/env bash

set -euo pipefail

detect_repo() {
  if ! git remote get-url origin >/dev/null 2>&1; then
    return 1
  fi
  python3 - <<'PY'
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
ENV_FILE="${2:-.env}"
PROFILES_FILE="${3:-digest_profiles.json}"
LOCAL_CODEX_CONFIG="${HOME}/.codex/config.toml"
BOOTSTRAP_CODEX_HOME="$(mktemp -d "${TMPDIR:-/tmp}/send-me-research-codex-home.XXXXXX")"
AUTH_FILE="${BOOTSTRAP_CODEX_HOME}/auth.json"
CONFIG_FILE="${BOOTSTRAP_CODEX_HOME}/config.toml"

cleanup() {
  rm -rf "${BOOTSTRAP_CODEX_HOME}"
}
trap cleanup EXIT

if [[ -z "${REPO}" ]]; then
  echo "Missing owner/repo. Pass it explicitly or set a GitHub origin remote first." >&2
  exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "Missing gh CLI." >&2
  exit 1
fi

if ! command -v codex >/dev/null 2>&1; then
  echo "Missing codex CLI." >&2
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

probe_codex_auth() {
  python3 - <<'PY'
import json
import subprocess
import sys
import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory(prefix="codex-auth-probe-") as temp_dir:
    temp_path = Path(temp_dir)
    schema_path = temp_path / "schema.json"
    output_path = temp_path / "output.json"
    schema_path.write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {"ok": {"type": "boolean"}},
                "required": ["ok"],
                "additionalProperties": False,
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            "codex",
            "exec",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--color",
            "never",
            "--ephemeral",
            "--model",
            "gpt-5.4",
            "--output-schema",
            str(schema_path),
            "-o",
            str(output_path),
            "-",
        ],
        input="Return a JSON object with ok=true.",
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr.strip() or result.stdout.strip() or "Codex auth probe failed.\n")
        raise SystemExit(1)
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    if payload.get("ok") is not True:
        sys.stderr.write("Codex auth probe returned an unexpected payload.\n")
        raise SystemExit(1)
PY
}

set -a
source "${ENV_FILE}"
set +a

if [[ -n "${CODEX_SECRET_SYNC_TOKEN:-}" ]]; then
  export GH_TOKEN="${CODEX_SECRET_SYNC_TOKEN}"
elif ! gh secret list --repo "${REPO}" | awk '{print $1}' | grep -qx CODEX_SECRET_SYNC_TOKEN; then
  echo "Missing CODEX_SECRET_SYNC_TOKEN. Set it in ${ENV_FILE} or as a GitHub Actions secret." >&2
  exit 1
fi

mkdir -p "${BOOTSTRAP_CODEX_HOME}"
if [[ -f "${LOCAL_CODEX_CONFIG}" ]]; then
  cp "${LOCAL_CODEX_CONFIG}" "${CONFIG_FILE}"
else
  : > "${CONFIG_FILE}"
fi

echo "Starting a fresh hosted-only Codex login. This does not use your normal ~/.codex/auth.json."
CODEX_HOME="${BOOTSTRAP_CODEX_HOME}" codex login --device-auth

CODEX_HOME="${BOOTSTRAP_CODEX_HOME}" probe_codex_auth

gh secret set CODEX_AUTH_JSON_BASE64 --repo "${REPO}" < <(base64_encode "${AUTH_FILE}")
gh secret set CODEX_CONFIG_TOML_BASE64 --repo "${REPO}" < <(base64_encode "${CONFIG_FILE}")
if [[ -n "${CODEX_SECRET_SYNC_TOKEN:-}" ]]; then
  gh secret set CODEX_SECRET_SYNC_TOKEN --repo "${REPO}" < <(printf '%s' "${CODEX_SECRET_SYNC_TOKEN}")
fi

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
echo "Hosted Codex auth was bootstrapped from a fresh CODEX_HOME and the local copy was discarded."
