from __future__ import annotations

import math
import sqlite3
import stat
from datetime import UTC, datetime

from jobloom import storage
from jobloom.errors import JobLoomError
from jobloom.jsonsafe import json_safe
from jobloom.models import Job
from jobloom.storage import connect, list_jobs, upsert_jobs
from jobloom.urls import canonicalize_url


def test_sqlite_upsert_dedupe_and_list(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    job = Job(
        source="jobspy-public:indeed",
        source_kind="public_search",
        source_id="same",
        title="Engineer",
        canonical_url="https://indeed.com/viewjob?jk=1",
        raw={"a": 1},
    )
    upsert_jobs([job])
    job.title = "Senior Engineer"
    upsert_jobs([job])
    rows = list_jobs(limit=10)
    assert len(rows) == 1
    assert rows[0].title == "Senior Engineer"


def test_sqlite_dedupe_prefers_canonical_url_when_source_id_later(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    first = Job(
        source="linkedin-linked",
        source_kind="platform_native_feed",
        canonical_url="https://linkedin.com/jobs/view/1",
        title="Engineer",
        raw={"a": 1},
    )
    second = Job(
        source="linkedin-linked",
        source_kind="platform_native_feed",
        source_id="1",
        canonical_url="https://linkedin.com/jobs/view/1",
        title="Senior Engineer",
        raw={"a": 2},
    )
    upsert_jobs([first])
    upsert_jobs([second])
    rows = list_jobs(limit=10)
    assert len(rows) == 1
    assert rows[0].title == "Senior Engineer"
    assert rows[0].source_id == "1"


def test_sqlite_file_permissions_and_symlink_rejection(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    db = tmp_path / "custom" / "jobs.sqlite3"
    upsert_jobs([Job(source="x", source_kind="test", title="T", raw={})], db_path=db)
    assert stat.S_IMODE(db.stat().st_mode) == 0o600
    assert stat.S_IMODE(db.parent.stat().st_mode) == 0o700

    link = tmp_path / "link.sqlite3"
    link.symlink_to(db)
    try:
        connect(link)
    except JobLoomError as exc:
        assert exc.code == "storage_error"
    else:
        raise AssertionError("symlink database path was not rejected")


def test_sqlite_rejects_newer_schema(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    db = tmp_path / "newer.sqlite3"
    raw = sqlite3.connect(db)
    raw.execute("PRAGMA user_version = 999")
    raw.close()
    try:
        connect(db)
    except JobLoomError as exc:
        assert exc.code == "storage_error"
        assert "newer than supported" in exc.message
    else:
        raise AssertionError("newer schema was not rejected")


def test_sqlite_connect_closes_connection_when_migration_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    class FakeConnection:
        row_factory = None

        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    fake = FakeConnection()

    def fail_migration(conn):
        assert conn is fake
        raise JobLoomError("boom", 5, "storage_error")

    monkeypatch.setattr(sqlite3, "connect", lambda _: fake)
    monkeypatch.setattr(storage, "migrate", fail_migration)
    try:
        connect(tmp_path / "fails.sqlite3")
    except JobLoomError:
        pass
    else:
        raise AssertionError("migration failure was not raised")
    assert fake.closed is True


def test_sqlite_initializes_schema_version_zero_to_one(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    db = tmp_path / "empty.sqlite3"
    conn = connect(db)
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    conn.close()
    assert version == 1


def test_url_canonicalization():
    assert (
        canonicalize_url("https://www.indeed.com/viewjob?jk=1&vjk=noise&utm_source=x")
        == "https://indeed.com/viewjob?jk=1"
    )
    assert (
        canonicalize_url("https://www.linkedin.com/jobs/view/1/?trk=x")
        == "https://linkedin.com/jobs/view/1"
    )


def test_json_safe_edge_cases():
    value = json_safe(
        {
            "nan": math.nan,
            "time": datetime(2024, 1, 1, tzinfo=UTC),
            "list": [1, None, float("inf")],
        }
    )
    assert "nan" not in value
    assert value["time"] == "2024-01-01T00:00:00+00:00"
    assert value["list"] == [1]
