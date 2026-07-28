from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Mapping
from typing import Any

from ..config import load_config
from ..errors import EXIT_PROVIDER, JobLoomError, redact, sanitize_raw
from ..jsonsafe import json_safe
from ..models import Job
from ..urls import canonicalize_url

DEFAULT_TIMEOUT = 20


def settings() -> tuple[str, int]:
    cfg = load_config().get("providers", {}).get("linkedin_linked", {})
    executable = cfg.get("executable", "linked")
    timeout = cfg.get("timeout_seconds", DEFAULT_TIMEOUT)
    if "command" in cfg or not isinstance(executable, str) or not executable:
        raise JobLoomError(
            "Invalid linkedin-linked executable config", EXIT_PROVIDER, "provider_config_invalid"
        )
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 300:
        raise JobLoomError(
            "Invalid linkedin-linked timeout_seconds config",
            EXIT_PROVIDER,
            "provider_config_invalid",
        )
    return executable, timeout


def available() -> bool:
    try:
        executable, _ = settings()
    except JobLoomError:
        return False
    return executable_available(executable)


def executable_available(exe: str) -> bool:
    if shutil.which(exe):
        return True
    return os.path.isabs(exe) and os.access(exe, os.X_OK)


def feed(limit: int) -> list[Job]:
    executable, timeout = settings()
    if not executable_available(executable):
        raise JobLoomError(
            "Optional linked executable is not available",
            EXIT_PROVIDER,
            "provider_unavailable",
            "Install and configure russ-blaisdell/linked yourself, then run `linked jobs recommended --count N -o json` directly to verify it.",
        )
    argv = [executable, "jobs", "recommended", "--count", str(limit), "-o", "json"]
    try:
        proc = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=provider_env(),
        )
    except subprocess.TimeoutExpired as exc:
        raise JobLoomError(
            f"linkedin-linked timed out after {timeout} seconds",
            EXIT_PROVIDER,
            "provider_timeout",
            redact(exc.stderr),
        ) from None
    except OSError as exc:
        raise JobLoomError(str(exc), EXIT_PROVIDER, "provider_unavailable") from None
    if proc.returncode != 0:
        raise JobLoomError(
            "linkedin-linked returned a non-zero exit status",
            EXIT_PROVIDER,
            "provider_failed",
            redact(proc.stderr),
        )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise JobLoomError(
            "linkedin-linked output was not valid JSON", EXIT_PROVIDER, "provider_output_drift"
        ) from None
    items = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise JobLoomError(
            "linkedin-linked JSON did not contain an items array",
            EXIT_PROVIDER,
            "provider_output_drift",
        )
    jobs: list[Job] = []
    for item in items:
        if not isinstance(item, Mapping):
            raise JobLoomError(
                "linkedin-linked items contained a non-object element",
                EXIT_PROVIDER,
                "provider_output_drift",
            )
        jobs.append(record_to_job(dict(item)))
    return jobs


def provider_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("LINKED_DEBUG", None)
    env["NO_COLOR"] = "1"
    return env


def record_to_job(record: dict[str, Any]) -> Job:
    safe = json_safe(sanitize_raw(record)) or {}
    if not isinstance(safe, dict):
        raise JobLoomError(
            "linkedin-linked item was malformed", EXIT_PROVIDER, "provider_output_drift"
        )
    url = first(safe, "url", "jobUrl", "job_url", "link", "posting_url")
    source_id = text(first(safe, "id", "job_id", "entityUrn", "urn"))
    if not url and source_id and source_id.isdecimal():
        url = f"https://www.linkedin.com/jobs/view/{source_id}"
    return Job(
        source="linkedin-linked",
        source_kind="platform_native_feed",
        source_id=source_id,
        canonical_url=canonicalize_url(str(url)) if url else None,
        title=text(first(safe, "title", "jobTitle")),
        company=nested_name(first(safe, "company", "companyName")),
        location=nested_name(first(safe, "location")),
        description=text(first(safe, "description")),
        posting_url=str(url) if url else None,
        apply_url=text(first(safe, "apply_url", "applyUrl")),
        remote=boolean(first(safe, "remote", "is_remote")),
        posted_at=text(first(safe, "posted_at", "postedAt", "listedAt", "date_posted")),
        raw=safe,
    )


def first(record: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = record.get(name)
        if value is not None:
            return value
    return None


def text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, int | float) and not isinstance(value, bool):
        return str(value)
    raise JobLoomError(
        "linkedin-linked item had malformed field shapes", EXIT_PROVIDER, "provider_output_drift"
    )


def boolean(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    raise JobLoomError(
        "linkedin-linked item had malformed field shapes", EXIT_PROVIDER, "provider_output_drift"
    )


def nested_name(value: Any) -> str | None:
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        for key in ("name", "localizedName", "companyName", "displayName", "title"):
            if key in value:
                return text(value[key])
    raise JobLoomError(
        "linkedin-linked item had malformed field shapes", EXIT_PROVIDER, "provider_output_drift"
    )
