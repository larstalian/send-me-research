from __future__ import annotations

import argparse
from datetime import date, datetime
import sys

from .codex_rank import CodexAuthError
from .config import AppSettings
from .service import DigestService


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Daily subscription-backed research digest.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    auth_check = subparsers.add_parser("auth-check", help="Verify Codex login state.")
    auth_check.set_defaults(handler=handle_auth_check)

    profiles = subparsers.add_parser("list-profiles", help="Show resolved digest profiles.")
    profiles.set_defaults(handler=handle_list_profiles)

    preview = subparsers.add_parser("preview-digest", help="Build digest artifacts without sending.")
    preview.add_argument("--date", dest="target_date", required=True, type=parse_date)
    preview.add_argument("--profile", dest="profile_name")
    preview.set_defaults(handler=handle_preview_digest)

    run = subparsers.add_parser("run-digest", help="Build a digest, optionally send it.")
    run.add_argument("--date", dest="target_date", required=True, type=parse_date)
    run.add_argument("--profile", dest="profile_name")
    run.add_argument("--send", action="store_true", help="Send the digest email after rendering.")
    run.set_defaults(handler=handle_run_digest)

    prune = subparsers.add_parser("prune-state", help="Prune old local state rows.")
    prune.add_argument("--days", dest="retention_days", type=int, default=60)
    prune.add_argument("--today", dest="today", type=parse_date)
    prune.set_defaults(handler=handle_prune_state)

    backfill = subparsers.add_parser("backfill", help="Preview digests across a date range.")
    backfill.add_argument("--from", dest="start_date", required=True, type=parse_date)
    backfill.add_argument("--to", dest="end_date", required=True, type=parse_date)
    backfill.add_argument("--profile", dest="profile_name")
    backfill.set_defaults(handler=handle_backfill)

    return parser


def handle_auth_check(args: argparse.Namespace) -> int:
    settings = AppSettings.from_env()
    service = DigestService(settings)
    try:
        print(service.auth_check())
        return 0
    finally:
        service.close()


def handle_preview_digest(args: argparse.Namespace) -> int:
    settings = AppSettings.from_env()
    service = DigestService(settings)
    try:
        results = service.preview_digests(target_date=args.target_date, profile_name=args.profile_name)
        _print_results(results, preview=True)
        return 0
    finally:
        service.close()


def handle_list_profiles(args: argparse.Namespace) -> int:
    settings = AppSettings.from_env()
    profiles = settings.load_profiles()
    for profile in profiles:
        recipients = ", ".join(profile.recipients) if profile.recipients else "(no recipients configured)"
        keywords = ", ".join(profile.priority_keywords[:5])
        print(f"{profile.name} [{profile.slug}]")
        print(f"  recipients: {recipients}")
        print(f"  top_n: {profile.top_n}")
        print(f"  focus: {keywords}")
    return 0


def handle_run_digest(args: argparse.Namespace) -> int:
    settings = AppSettings.from_env()
    service = DigestService(settings)
    try:
        try:
            results = service.run_digests(target_date=args.target_date, send=args.send, profile_name=args.profile_name)
        except CodexAuthError as error:
            if args.send:
                service.send_failure_email(
                    target_date=args.target_date,
                    error=error,
                    profiles=settings.resolve_profiles(args.profile_name),
                )
            raise
        _print_results(results, preview=False, sent=args.send)
        return 0
    finally:
        service.close()


def handle_prune_state(args: argparse.Namespace) -> int:
    settings = AppSettings.from_env()
    service = DigestService(settings)
    try:
        service.state.prune(retention_days=args.retention_days, today=args.today)
        print(f"State pruned to the last {args.retention_days} days in {service.state.state_dir}.")
        return 0
    finally:
        service.close()


def handle_backfill(args: argparse.Namespace) -> int:
    settings = AppSettings.from_env()
    service = DigestService(settings)
    try:
        results = service.backfill(start_date=args.start_date, end_date=args.end_date, profile_name=args.profile_name)
        for result in results:
            print(f"{result.profile_name} {result.digest_date.isoformat()}: {len(result.entries)} entries -> {result.output_dir}")
        return 0
    finally:
        service.close()


def _print_results(results, *, preview: bool, sent: bool = False) -> None:
    multi = len(results) > 1
    for result in results:
        if multi:
            print(f"[{result.profile_name}]")
        if preview:
            print(f"Preview complete: {result.html_path}")
        else:
            print(f"Digest output: {result.output_dir}")
            print(f"HTML: {result.html_path}")
        print(f"Entries: {len(result.entries)}")
        if not preview:
            if result.skipped_send:
                print("Send skipped because this digest date was already recorded as sent for this profile.")
            elif sent:
                print("Digest email sent.")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        code = args.handler(args)
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
    raise SystemExit(code)
