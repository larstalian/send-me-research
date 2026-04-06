# Send Me Research

Daily Codex-backed paper digests for:

- LLMs
- agents
- robotics / embodied AI
- cyber / AI security

It pulls fresh papers from arXiv and OpenAlex, dedupes them, lets Codex rank the interesting ones, and sends a clean HTML email.

## Quick Start

1. Install `uv` and Codex CLI.
2. Run `codex login`.
3. Copy `.env.example` to `.env` and fill in SMTP settings.
4. Sync deps:

```bash
uv sync --group dev
```

5. Pick a date:

```bash
TARGET_DATE="$(TZ=America/Los_Angeles date +%F)"
```

6. Preview:

```bash
set -a
source .env
set +a
uv run send-me-research preview-digest --date "$TARGET_DATE"
```

7. Send:

```bash
set -a
source .env
set +a
uv run send-me-research run-digest --date "$TARGET_DATE" --send
```

## Default Behavior

If you do nothing beyond `.env`, the app sends one digest to `EMAIL_TO` using the built-in default audience:

- LLMs
- agents
- robotics
- cyber / security
- extra weight on post-training, fine-tuning, code generation, tool use, and agentic-task improvement

## Multiple People, Different Stacks

Create `digest_profiles.json` from `digest_profiles.example.json`.

Each profile can set:

- `name`
- `recipients`
- `description`
- `priority_keywords`
- `top_n`

Example:

```json
{
  "profiles": [
    {
      "name": "Applied ML",
      "recipients": ["ml@example.com"],
      "description": "LLMs, agents, post-training, code generation, and evaluation.",
      "priority_keywords": ["fine-tuning", "post-training", "code generation"],
      "top_n": 15
    },
    {
      "name": "Security",
      "recipients": ["security@example.com"],
      "description": "Prompt injection, jailbreaks, agent security, and AI red teaming.",
      "priority_keywords": ["prompt injection", "jailbreak", "red teaming"],
      "top_n": 10
    }
  ]
}
```

Useful commands:

```bash
uv run send-me-research list-profiles
uv run send-me-research preview-digest --date "$TARGET_DATE"
uv run send-me-research preview-digest --date "$TARGET_DATE" --profile Security
uv run send-me-research run-digest --date "$TARGET_DATE" --send
```

If `digest_profiles.json` is absent, the app falls back to the default single profile from `.env`.

## Gmail

Use a Google app password, not your normal Gmail password.

Required mail env:

- `EMAIL_FROM`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`

`EMAIL_TO` is only needed when you are not using profile config.

## GitHub Actions

Two workflows are included:

- `.github/workflows/daily-digest-hosted.yml`: GitHub-hosted runner using restored Codex auth
- `.github/workflows/daily-digest.yml`: self-hosted runner using persistent `~/.codex`

Hosted mode is the easiest path if you want a clean public repo and no daily commits.

Set these secrets:

- `CODEX_AUTH_JSON_BASE64`
- `CODEX_CONFIG_TOML_BASE64`
- `EMAIL_FROM`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `EMAIL_TO` optional
- `DIGEST_PROFILES_JSON` optional
- `OPENALEX_MAILTO` optional

If `DIGEST_PROFILES_JSON` is set, the workflow uses that instead of a checked-in `digest_profiles.json`. That is the easiest way to keep recipient emails private in a public repo.

Helper:

```bash
./scripts/sync_github_hosted_secrets.sh
```

That script uploads Codex auth, mail secrets from `.env`, and `digest_profiles.json` if it exists.

## State

The workflows do not commit state back to git. They restore the latest state artifact, use it for dedupe, prune it, and upload a fresh artifact after each run.

Local scratch paths:

- `state/`
- `out/`

Neither is tracked in git.
