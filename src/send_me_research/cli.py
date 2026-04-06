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

    preview = subparsers.add_parser("preview-digest", help="Build digest artifacts without sending.")
    preview.add_argument("--date", dest="target_date", required=True, type=parse_date)
    preview.set_defaults(handler=handle_preview_digest)

    run = subparsers.add_parser("run-digest", help="Build a digest, optionally send it.")
    run.add_argument("--date", dest="target_date", required=True, type=parse_date)
    run.add_argument("--send", action="store_true", help="Send the digest email after rendering.")
    run.set_defaults(handler=handle_run_digest)

    backfill = subparsers.add_parser("backfill", help="Preview digests across a date range.")
    backfill.add_argument("--from", dest="start_date", required=True, type=parse_date)
    backfill.add_argument("--to", dest="end_date", required=True, type=parse_date)
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
        result = service.preview_digest(target_date=args.target_date)
        print(f"Preview complete: {result.html_path}")
        print(f"PDF written to: {result.pdf_path}")
        print(f"Entries: {len(result.entries)}")
        return 0
    finally:
        service.close()


def handle_run_digest(args: argparse.Namespace) -> int:
    settings = AppSettings.from_env()
    service = DigestService(settings)
    try:
        try:
            result = service.run_digest(target_date=args.target_date, send=args.send)
        except CodexAuthError as error:
            if args.send:
                service.send_failure_email(target_date=args.target_date, error=error)
            raise
        print(f"Digest output: {result.output_dir}")
        print(f"HTML: {result.html_path}")
        print(f"PDF: {result.pdf_path}")
        print(f"Entries: {len(result.entries)}")
        if result.skipped_send:
            print("Send skipped because this digest date was already recorded as sent.")
        elif args.send:
            print("Digest email sent.")
        return 0
    finally:
        service.close()


def handle_backfill(args: argparse.Namespace) -> int:
    settings = AppSettings.from_env()
    service = DigestService(settings)
    try:
        results = service.backfill(start_date=args.start_date, end_date=args.end_date)
        for result in results:
            print(f"{result.digest_date.isoformat()}: {len(result.entries)} entries -> {result.output_dir}")
        return 0
    finally:
        service.close()


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        code = args.handler(args)
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
    raise SystemExit(code)
