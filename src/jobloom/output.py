from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any


def emit(data: Any, fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(data, sort_keys=True, separators=(",", ":")))
    elif fmt == "ndjson":
        rows = data if isinstance(data, list) else [data]
        for row in rows:
            print(json.dumps(row, sort_keys=True, separators=(",", ":")))
    else:
        print_table(data if isinstance(data, list) else [data])


def print_table(rows: Iterable[dict[str, Any]]) -> None:
    materialized = list(rows)
    if not materialized:
        print("No rows")
        return
    keys = table_keys(materialized)
    widths = {
        key: max(len(key), *(len(format_cell(row.get(key))) for row in materialized))
        for key in keys
    }
    print("  ".join(key.ljust(widths[key]) for key in keys))
    print("  ".join("-" * widths[key] for key in keys))
    for row in materialized:
        print("  ".join(format_cell(row.get(key)).ljust(widths[key]) for key in keys))


def table_keys(rows: list[dict[str, Any]]) -> list[str]:
    job_keys = ["source", "title", "company", "location", "canonical_url"]
    if any(any(key in row for key in job_keys) for row in rows):
        return job_keys
    keys: list[str] = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    return keys


def format_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict | list):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return str(value)
