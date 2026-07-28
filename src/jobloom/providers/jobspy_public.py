from __future__ import annotations

import contextlib
import io
from typing import Any

from ..errors import EXIT_UPSTREAM, JobLoomError, redact, sanitize_raw
from ..jsonsafe import json_safe
from ..models import Job
from ..urls import canonicalize_url

SITE_CHOICES = ("linkedin", "indeed", "glassdoor", "zip_recruiter", "google")


def search_jobs(
    query: str,
    sites: list[str],
    location: str,
    country: str,
    limit: int,
    hours_old: int | None = None,
    remote: bool = False,
    job_type: str | None = None,
    fetch_linkedin_description: bool = False,
) -> list[Job]:
    try:
        from jobspy import scrape_jobs
    except Exception as exc:
        raise JobLoomError(redact(str(exc)), EXIT_UPSTREAM, "jobspy_unavailable") from None

    kwargs: dict[str, Any] = {
        "site_name": sites,
        "search_term": query,
        "location": location,
        "country_indeed": country,
        "results_wanted": limit,
    }
    if hours_old is not None:
        kwargs["hours_old"] = hours_old
    if remote:
        kwargs["is_remote"] = True
    if job_type:
        kwargs["job_type"] = job_type
    if fetch_linkedin_description:
        kwargs["linkedin_fetch_description"] = True

    stdout = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout):
            result = scrape_jobs(**kwargs)
    except Exception as exc:
        raise JobLoomError(redact(str(exc)), EXIT_UPSTREAM, "jobspy_search_failed") from None
    return normalize_jobspy(result)


def normalize_jobspy(result: Any) -> list[Job]:
    if hasattr(result, "to_dict"):
        records = result.to_dict(orient="records")
    elif isinstance(result, list):
        records = result
    else:
        records = list(result)
    return [record_to_job(record) for record in records]


def pick(record: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in record and json_safe(record[name]) is not None:
            return json_safe(record[name])
    return None


def record_to_job(record: dict[str, Any]) -> Job:
    safe = json_safe(sanitize_raw(record)) or {}
    source = str(pick(safe, "site", "site_name", "source") or "jobspy-public")
    posting_url = pick(safe, "job_url", "job_url_direct", "url", "posting_url")
    return Job(
        source=f"jobspy-public:{source}",
        source_kind="public_search",
        source_id=str(pick(safe, "id", "job_id") or "") or None,
        canonical_url=canonicalize_url(str(posting_url)) if posting_url else None,
        title=pick(safe, "title", "job_title"),
        company=pick(safe, "company", "company_name"),
        location=pick(safe, "location"),
        description=pick(safe, "description", "job_description"),
        posting_url=str(posting_url) if posting_url else None,
        apply_url=pick(safe, "job_url_direct", "apply_url"),
        remote=bool(pick(safe, "is_remote")) if pick(safe, "is_remote") is not None else None,
        posted_at=pick(safe, "date_posted", "posted_at"),
        raw=safe,
    )
