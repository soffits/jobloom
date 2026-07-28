from __future__ import annotations

import contextlib
import json
import os
import sqlite3
from pathlib import Path

from .config import ensure_private_dir, paths
from .errors import EXIT_STATE, JobLoomError
from .models import Job, utc_now_iso

SCHEMA_VERSION = 1


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    p = paths()
    database = db_path or p.database_file
    try:
        try:
            ensure_private_dir(p.state_dir if db_path is None else database.parent)
        except JobLoomError as exc:
            raise JobLoomError(exc.message, EXIT_STATE, "storage_error", exc.hint) from None
        prepare_database_file(database)
        conn = sqlite3.connect(database)
        conn.row_factory = sqlite3.Row
        with contextlib.suppress(OSError):
            database.chmod(0o600)
        try:
            migrate(conn)
        except BaseException:
            conn.close()
            raise
        return conn
    except sqlite3.Error as exc:
        raise JobLoomError(str(exc), EXIT_STATE, "storage_error") from None
    except OSError as exc:
        raise JobLoomError(str(exc), EXIT_STATE, "storage_error") from None


def prepare_database_file(database: Path) -> None:
    if database.is_symlink():
        raise JobLoomError(
            f"Refusing to open symlink database at {database}", EXIT_STATE, "storage_error"
        )
    if database.exists():
        return
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(database, flags, 0o600)
    os.close(fd)


def migrate(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        raise JobLoomError(
            f"Database schema version {version} is newer than supported version {SCHEMA_VERSION}",
            EXIT_STATE,
            "storage_error",
        )
    migrations = {0: migrate_v0_to_v1}
    while version < SCHEMA_VERSION:
        migrations[version](conn)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
    conn.commit()


def migrate_v0_to_v1(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY,
            dedupe_key TEXT NOT NULL UNIQUE,
            source TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            source_id TEXT,
            canonical_url TEXT,
            title TEXT,
            company TEXT,
            location TEXT,
            description TEXT,
            posting_url TEXT,
            apply_url TEXT,
            remote INTEGER,
            posted_at TEXT,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            raw_json TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source)")
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def dedupe_key(job: Job) -> str:
    if job.canonical_url:
        return f"url:{job.canonical_url}"
    if job.source_id:
        return f"source:{job.source}:{job.source_id}"
    basis = "|".join([job.source, job.title or "", job.company or "", job.location or ""])
    return f"fields:{basis}"


def upsert_jobs(jobs: list[Job], db_path: Path | None = None) -> list[Job]:
    if not jobs:
        return []
    conn = connect(db_path)
    now = utc_now_iso()
    try:
        for job in jobs:
            if not job.first_seen:
                job.first_seen = now
            job.last_seen = now
            conn.execute(
                """
                INSERT INTO jobs (
                    dedupe_key, source, source_kind, source_id, canonical_url, title, company,
                    location, description, posting_url, apply_url, remote, posted_at,
                    first_seen, last_seen, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dedupe_key) DO UPDATE SET
                    source=excluded.source,
                    source_kind=excluded.source_kind,
                    source_id=excluded.source_id,
                    canonical_url=excluded.canonical_url,
                    title=excluded.title,
                    company=excluded.company,
                    location=excluded.location,
                    description=excluded.description,
                    posting_url=excluded.posting_url,
                    apply_url=excluded.apply_url,
                    remote=excluded.remote,
                    posted_at=excluded.posted_at,
                    last_seen=excluded.last_seen,
                    raw_json=excluded.raw_json
                """,
                (
                    dedupe_key(job),
                    job.source,
                    job.source_kind,
                    job.source_id,
                    job.canonical_url,
                    job.title,
                    job.company,
                    job.location,
                    job.description,
                    job.posting_url,
                    job.apply_url,
                    None if job.remote is None else int(job.remote),
                    job.posted_at,
                    job.first_seen,
                    job.last_seen,
                    json.dumps(job.raw, sort_keys=True),
                ),
            )
        conn.commit()
        return jobs
    except sqlite3.Error as exc:
        raise JobLoomError(str(exc), EXIT_STATE, "storage_error") from None
    finally:
        conn.close()


def list_jobs(source: str | None = None, limit: int = 50, db_path: Path | None = None) -> list[Job]:
    conn = connect(db_path)
    try:
        if source:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE source = ? ORDER BY last_seen DESC LIMIT ?",
                (source, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY last_seen DESC LIMIT ?", (limit,)
            ).fetchall()
        return [row_to_job(row) for row in rows]
    except sqlite3.Error as exc:
        raise JobLoomError(str(exc), EXIT_STATE, "storage_error") from None
    finally:
        conn.close()


def row_to_job(row: sqlite3.Row) -> Job:
    return Job(
        source=row["source"],
        source_kind=row["source_kind"],
        source_id=row["source_id"],
        canonical_url=row["canonical_url"],
        title=row["title"],
        company=row["company"],
        location=row["location"],
        description=row["description"],
        posting_url=row["posting_url"],
        apply_url=row["apply_url"],
        remote=None if row["remote"] is None else bool(row["remote"]),
        posted_at=row["posted_at"],
        first_seen=row["first_seen"],
        last_seen=row["last_seen"],
        raw=json.loads(row["raw_json"]),
    )
