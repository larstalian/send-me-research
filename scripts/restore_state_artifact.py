#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen
import zipfile


STATE_FILES = {"papers_seen.jsonl", "digests_sent.jsonl"}


class NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def github_get_json(url: str, token: str) -> dict:
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "send-me-research",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urlopen(request) as response:
        return json.load(response)


def github_get_bytes(url: str, token: str) -> bytes:
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "send-me-research",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    opener = build_opener(NoRedirectHandler())
    try:
        with opener.open(request) as response:
            redirect_url = response.headers.get("Location")
    except HTTPError as error:
        if error.code not in {301, 302, 303, 307, 308}:
            raise
        redirect_url = error.headers.get("Location")

    if not redirect_url:
        raise RuntimeError(f"Artifact download endpoint returned no redirect location for {url}")

    blob_request = Request(
        redirect_url,
        headers={
            "User-Agent": "send-me-research",
        },
    )
    with urlopen(blob_request) as response:
        return response.read()


def list_artifacts(repo: str, token: str) -> list[dict]:
    page = 1
    artifacts: list[dict] = []
    while True:
        payload = github_get_json(
            f"https://api.github.com/repos/{repo}/actions/artifacts?per_page=100&page={page}",
            token,
        )
        page_items = payload.get("artifacts", [])
        if not page_items:
            break
        artifacts.extend(page_items)
        if len(page_items) < 100:
            break
        page += 1
    return artifacts


def restore_state(repo: str, token: str, artifact_name: str, state_dir: Path) -> int:
    artifacts = [
        artifact
        for artifact in list_artifacts(repo, token)
        if artifact.get("name") == artifact_name and not artifact.get("expired", False)
    ]
    if not artifacts:
        print(f"No prior state artifact named '{artifact_name}' found. Starting fresh.")
        return 0

    artifact = max(artifacts, key=lambda item: (item.get("created_at", ""), item.get("id", 0)))
    archive = github_get_bytes(str(artifact["archive_download_url"]), token)

    state_dir.mkdir(parents=True, exist_ok=True)
    for name in STATE_FILES:
        target = state_dir / name
        if target.exists():
            target.unlink()

    restored = 0
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        for member in bundle.infolist():
            if member.is_dir():
                continue
            basename = Path(member.filename).name
            if basename not in STATE_FILES:
                continue
            (state_dir / basename).write_bytes(bundle.read(member))
            restored += 1

    print(
        f"Restored {restored} state file(s) from artifact #{artifact['id']} "
        f"created at {artifact.get('created_at', 'unknown time')}."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore the latest state artifact from GitHub Actions.")
    parser.add_argument("--repo", required=True, help="owner/name")
    parser.add_argument("--artifact-name", required=True)
    parser.add_argument("--state-dir", default="state")
    args = parser.parse_args()

    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GITHUB_TOKEN is required to restore state artifacts.")

    try:
        return restore_state(
            repo=args.repo,
            token=token,
            artifact_name=args.artifact_name,
            state_dir=Path(args.state_dir),
        )
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise SystemExit(f"GitHub API error restoring state artifact: {error.code} {detail}") from error


if __name__ == "__main__":
    raise SystemExit(main())
