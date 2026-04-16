# Send Me Research

Configurable daily research digests powered by Codex.

This project automatically watches fresh papers from arXiv and OpenAlex every day, dedupes them, lets Codex decide what is actually worth reading, and sends polished HTML email digests to one or more recipients.

It is built around a specific deployment trick: the hosted GitHub Actions workflow can reuse your existing Codex ChatGPT login by restoring a minimal `~/.codex` home from GitHub secrets. That means the ranking step can run in Actions without switching the project over to an OpenAI API key.

A live sample digest is published at [larstalian.github.io/send-me-research](https://larstalian.github.io/send-me-research/).

You can run it in two modes:

- one default digest from `.env`
- multiple custom digests with different recipients and different research priorities

Out of the box, the default audience is:

- LLMs
- agents
- robotics / embodied AI
- cyber / AI security

with extra weight on post-training, fine-tuning, code generation, tool use, and agentic-task improvement. You can keep that default, or define completely different stacks per recipient in [`digest_profiles.example.json`](digest_profiles.example.json) or the [Multiple People, Different Stacks](#multiple-people-different-stacks) section below.

## Setup

1. Install `uv` and the Codex CLI.
2. Run `codex login`.
3. Copy `.env.example` to `.env`.
4. Fill in your SMTP settings.
5. Install deps:

```bash
uv sync
```

Use Gmail with an app password, not your normal password.

## Default Mode

If you only use `.env`, the app sends one digest to `EMAIL_TO` using the built-in default audience:

- LLMs
- agents
- robotics
- cyber / security
- extra weight on post-training, fine-tuning, code generation, tool use, and agentic-task improvement

That is the fastest path if this is mainly for you.

## Multiple People, Different Stacks

Create `digest_profiles.json` from `digest_profiles.example.json`.

Each profile can define:

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

If `digest_profiles.json` is present, the app sends one digest per profile. If it is absent, the app falls back to the default single profile from `.env`.

## Local Commands

Pick a date:

```bash
TARGET_DATE="$(TZ=America/Los_Angeles date +%F)"
```

Load env:

```bash
set -a
source .env
set +a
```

Preview:

```bash
uv run send-me-research preview-digest --date "$TARGET_DATE"
```

Send:

```bash
uv run send-me-research run-digest --date "$TARGET_DATE" --send
```

Preview one profile only:

```bash
uv run send-me-research preview-digest --date "$TARGET_DATE" --profile Security
```

See resolved profiles:

```bash
uv run send-me-research list-profiles
```

Run tests:

```bash
uv run pytest -q
```

## Required Env

Always required:

- `EMAIL_FROM`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`

Only required when you are not using profile config:

- `EMAIL_TO`

Common optional settings:

- `DIGEST_TIMEZONE`
- `CODEX_ENABLE_SEARCH`
- `CODEX_ENABLE_WILDCARD_DISCOVERY`
- `TOP_N`
- `CODEX_SHORTLIST_SIZE`
- `ROBOTICS_SPOTLIGHT_COUNT`

## GitHub Actions

Two workflows are included:

- `.github/workflows/daily-digest-hosted.yml`
- `.github/workflows/daily-digest.yml`

Hosted mode is the recommended setup if you want:

- a public repo
- no daily commits for state
- no always-on self-hosted runner

### Hosted Setup

Set these GitHub secrets:

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

Best path:

```bash
./scripts/sync_github_hosted_secrets.sh
```

That script:

- uploads your minimal Codex auth
- uploads mail secrets from `.env`
- uploads `digest_profiles.json` as `DIGEST_PROFILES_JSON` if the file exists
- sets `DIGEST_AUTOMATION_MODE=hosted`
- refuses to sync if your local Codex session cannot pass a real `codex exec` probe

If `DIGEST_PROFILES_JSON` is set, the workflow uses that instead of a checked-in `digest_profiles.json`. That is the cleanest way to keep recipient emails and audience configs private in a public repo.

Hosted Codex auth is a snapshot, not a permanent token. If the workflow later fails with a Codex auth error, run `codex login` again locally and then rerun `./scripts/sync_github_hosted_secrets.sh`.

## State And Outputs

The workflows do not commit state back to git. They restore the latest state artifact, use it for dedupe, prune it, and upload a fresh artifact after each run.

Local scratch paths:

- `state/`
- `out/`

Neither is tracked in git.
