# Send Me Research

Daily paper digest for:

- LLMs
- agents
- robotics / embodied AI
- cyber / AI security

It collects new papers from arXiv and OpenAlex, dedupes them, lets Codex rank and annotate the shortlist, then sends a clean HTML email with a PDF attachment.

## Stack

- Python 3.11
- `uv`
- Codex CLI
- Gmail SMTP

## Local Quick Start

1. Install `uv`, Docker, and Codex CLI.
2. Run `codex login`.
3. Copy `.env.example` to `.env` and fill it in.
4. Sync deps:

```bash
uv sync --group dev
```

5. Preview a digest:

```bash
set -a
source .env
set +a
uv run send-me-research preview-digest --date 2026-04-06
```

6. Send a digest:

```bash
set -a
source .env
set +a
uv run send-me-research run-digest --date 2026-04-06 --send
```

7. Run tests:

```bash
uv run pytest -q
```

## Required Env Vars

- `EMAIL_TO`
- `EMAIL_FROM`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`

Useful optional vars:

- `DIGEST_TIMEZONE` default: `America/Los_Angeles`
- `CODEX_ENABLE_SEARCH` default: `true`
- `CODEX_ENABLE_WILDCARD_DISCOVERY` default: `true`
- `STATE_RETENTION_DAYS` default: `60`
- `TOP_N` default: `15`
- `ROBOTICS_SPOTLIGHT_COUNT` default: `2`

## Gmail

Use a Google app password, not your normal Gmail password.

## Automation Modes

There are two workflows:

- `.github/workflows/daily-digest.yml`
  Uses a self-hosted runner with persistent `~/.codex`
- `.github/workflows/daily-digest-hosted.yml`
  Uses `ubuntu-latest` and restores a minimal Codex home from GitHub secrets

Set the GitHub repo variable:

- `DIGEST_AUTOMATION_MODE=self-hosted`
- `DIGEST_AUTOMATION_MODE=hosted`

If unset, scheduled runs default to `self-hosted`.

Both workflows are scheduled for 8:00 AM `America/Los_Angeles` and guard against duplicate UTC cron triggers.

Workflow state is not committed to git anymore. Each run restores the newest `digest-state-*` Actions artifact, uses it for dedupe, prunes it to a rolling retention window, and uploads a fresh state artifact at the end.

## Hosted Runner Workaround

The hosted workflow is a workaround, not the official clean CI path.

What it restores:

- `~/.codex/auth.json`
- `~/.codex/config.toml`

That is enough for `codex login status` and `codex exec` to work on a fresh runner.

Security note:

- these secrets are sensitive
- if Codex login changes or expires, refresh them
- only scheduled/manual workflows here use the secrets

## Sync Hosted Secrets

Best path:

```bash
./scripts/sync_github_hosted_secrets.sh
```

That script:

- uploads minimal Codex auth to GitHub secrets
- uploads mail secrets from `.env`
- sets `DIGEST_AUTOMATION_MODE=hosted`

Manual fallback:

```bash
./scripts/print_codex_auth_secrets.sh
```

Then create these repo secrets yourself:

- `CODEX_AUTH_JSON_BASE64`
- `CODEX_CONFIG_TOML_BASE64`
- `EMAIL_TO`
- `EMAIL_FROM`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `OPENALEX_MAILTO` optional

## Repo Layout

- `src/send_me_research/` app code
- `templates/` HTML template
- `state/` local scratch state only
- `out/` generated local outputs
- `scripts/` secret/bootstrap helpers

`out/` is intentionally not tracked in git anymore. Workflow runs upload digest files as GitHub Actions artifacts instead, and automation state now lives in rolling Actions artifacts instead of git commits.
