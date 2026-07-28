from __future__ import annotations

import argparse
import json
import signal
import sys
from typing import Any

from . import __version__
from .config import init_files, mode, paths
from .errors import EXIT_USAGE, JobLoomError, fail
from .models import Job
from .output import emit
from .providers import indeed_native, jobspy_public, linkedin_linked
from .storage import list_jobs, upsert_jobs

JSON_FORMATS = ("json", "ndjson", "table")


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        print(
            json.dumps({"error": {"code": "usage", "message": message}}, sort_keys=True),
            file=sys.stderr,
        )
        raise SystemExit(EXIT_USAGE)


def build_parser() -> argparse.ArgumentParser:
    parser = Parser(prog="jobloom", description="Local-first, agent-friendly job discovery CLI.")
    parser.add_argument("--version", action="version", version=f"jobloom {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init")
    p_init.add_argument("--force", action="store_true")
    p_init.add_argument("--format", choices=("json", "table"), default="json")

    p_search = sub.add_parser("search")
    p_search.add_argument("query")
    p_search.add_argument(
        "--site", action="append", choices=jobspy_public.SITE_CHOICES, default=None
    )
    p_search.add_argument("--location", required=True)
    p_search.add_argument("--country", required=True)
    p_search.add_argument("--limit", type=positive_int, default=25)
    p_search.add_argument("--hours-old", type=positive_int)
    p_search.add_argument("--remote", action="store_true")
    p_search.add_argument("--job-type")
    p_search.add_argument("--fetch-linkedin-description", action="store_true")
    p_search.add_argument("--save", action="store_true")
    p_search.add_argument("--format", choices=JSON_FORMATS, default="json")

    p_feed = sub.add_parser("feed")
    p_feed.add_argument("source", choices=("linkedin", "indeed"))
    p_feed.add_argument("--limit", type=positive_int, default=25)
    p_feed.add_argument("--save", action="store_true")
    p_feed.add_argument("--format", choices=JSON_FORMATS, default="json")

    p_jobs = sub.add_parser("jobs")
    jobs_sub = p_jobs.add_subparsers(dest="jobs_command", required=True)
    p_list = jobs_sub.add_parser("list")
    p_list.add_argument("--source")
    p_list.add_argument("--limit", type=positive_int, default=50)
    p_list.add_argument("--format", choices=JSON_FORMATS, default="json")

    p_doctor = sub.add_parser("doctor")
    p_doctor.add_argument("--format", choices=("json", "table"), default="json")

    p_providers = sub.add_parser("providers")
    p_providers.add_argument("--format", choices=("json", "table"), default="json")
    return parser


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be a positive integer") from None
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def main(argv: list[str] | None = None) -> int:
    signal.signal(signal.SIGINT, handle_sigint)
    parser = build_parser()
    args = parser.parse_args(argv)
    fmt = getattr(args, "format", "json")
    try:
        result = dispatch(args)
    except JobLoomError as exc:
        fail(exc, fmt)
    emit(result, fmt)
    return 0


def handle_sigint(_signum: int, _frame: Any) -> None:
    print(
        json.dumps({"error": {"code": "interrupted", "message": "Interrupted"}}, sort_keys=True),
        file=sys.stderr,
    )
    raise SystemExit(130)


def dispatch(args: argparse.Namespace) -> Any:
    if args.command == "init":
        p = init_files(force=args.force)
        return {"config_file": str(p.config_file), "state_dir": str(p.state_dir), "created": True}
    if args.command == "search":
        jobs = jobspy_public.search_jobs(
            query=args.query,
            sites=args.site or ["linkedin", "indeed"],
            location=args.location,
            country=args.country,
            limit=args.limit,
            hours_old=args.hours_old,
            remote=args.remote,
            job_type=args.job_type,
            fetch_linkedin_description=args.fetch_linkedin_description,
        )
        return serialize_saved(jobs, args.save)
    if args.command == "feed":
        if args.source == "indeed":
            indeed_native.feed_unavailable()
        jobs = linkedin_linked.feed(args.limit)
        return serialize_saved(jobs, args.save)
    if args.command == "jobs" and args.jobs_command == "list":
        return [job.to_dict() for job in list_jobs(source=args.source, limit=args.limit)]
    if args.command == "doctor":
        return doctor()
    if args.command == "providers":
        return providers()
    raise JobLoomError("Unknown command", EXIT_USAGE, "usage")


def serialize_saved(jobs: list[Job], save: bool) -> list[dict[str, Any]]:
    if save:
        upsert_jobs(jobs)
    return [job.to_dict() for job in jobs]


def doctor() -> dict[str, Any]:
    p = paths()
    return {
        "config": {
            "path": str(p.config_file),
            "exists": safe_exists(p.config_file),
            "mode": mode(p.config_file),
        },
        "state": {
            "path": str(p.state_dir),
            "exists": safe_exists(p.state_dir),
            "mode": mode(p.state_dir),
        },
        "database": {
            "path": str(p.database_file),
            "exists": safe_exists(p.database_file),
            "mode": mode(p.database_file),
        },
        "linked_executable": {"available": linkedin_linked.available()},
    }


def providers() -> list[dict[str, Any]]:
    return [
        {
            "name": "jobspy-public",
            "available": True,
            "status": "package dependency; network not checked",
            "native_personalized_feed": False,
        },
        {
            "name": "linkedin-linked",
            "available": linkedin_linked.available(),
            "status": "optional external command; not executed by providers check",
            "native_personalized_feed": True,
        },
        {
            "name": "indeed-native",
            "available": False,
            "status": "unavailable; no verified native provider exists",
            "native_personalized_feed": True,
        },
    ]


def safe_exists(path: Any) -> bool:
    try:
        return path.exists()
    except OSError as exc:
        raise JobLoomError(str(exc), 3, "config_error") from None


if __name__ == "__main__":
    raise SystemExit(main())
