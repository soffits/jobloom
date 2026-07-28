from __future__ import annotations

import json
import sqlite3
import sys
import types

from conftest import ROOT, cli

from jobloom.providers import jobspy_public


class FakeFrame:
    def to_dict(self, orient: str):
        assert orient == "records"
        return [
            {
                "site": "linkedin",
                "id": "abc",
                "title": "Engineer",
                "company": "Acme",
                "location": "Remote",
                "job_url": "https://www.linkedin.com/jobs/view/123/?trk=public_jobs&x=1",
                "is_remote": True,
            }
        ]


def test_jobspy_search_suppresses_stdout_and_normalizes(monkeypatch, capsys):
    def scrape_jobs(**kwargs):
        print("jobspy chatter")
        assert kwargs["site_name"] == ["linkedin"]
        return FakeFrame()

    monkeypatch.setitem(sys.modules, "jobspy", types.SimpleNamespace(scrape_jobs=scrape_jobs))
    jobs = jobspy_public.search_jobs("python", ["linkedin"], "Remote", "USA", 1)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert jobs[0].source == "jobspy-public:linkedin"
    assert jobs[0].source_kind == "public_search"
    assert jobs[0].canonical_url == "https://linkedin.com/jobs/view/123?x=1"


def test_jobspy_record_is_sanitized_before_normalized_or_stored():
    record = {
        "site": "linkedin",
        "id": "abc",
        "title": "Engineer",
        "company": "Acme",
        "location": "Remote",
        "job_url": "https://example.com/jobs/1?access_token=url-secret&x=1",
        "apply_url": "https://example.com/apply?password=url-password&ok=1",
        "description": "Authorization: Bearer bearer-secret",
        "access_token": "raw-token",
        "nested": {"cookie": "raw-cookie", "safe": "value"},
        "is_remote": True,
    }

    job = jobspy_public.record_to_job(record)
    payload = json.dumps(job.to_dict(), sort_keys=True)

    assert job.posting_url == "https://example.com/jobs/1?x=1"
    assert job.apply_url == "https://example.com/apply?ok=1"
    assert "url-secret" not in payload
    assert "url-password" not in payload
    assert "raw-token" not in payload
    assert "raw-cookie" not in payload
    assert "bearer-secret" not in payload
    assert "access_token" not in job.raw
    assert "cookie" not in job.raw["nested"]


def test_jobspy_cli_save_never_outputs_or_stores_secrets(tmp_path):
    fake = tmp_path / "jobspy.py"
    fake.write_text(
        "def scrape_jobs(**kwargs):\n"
        "    print('token=stdout-secret')\n"
        "    return [{\n"
        "        'site': 'linkedin',\n"
        "        'id': 'abc',\n"
        "        'title': 'Engineer',\n"
        "        'job_url': 'https://example.com/jobs/1?token=url-secret&x=1',\n"
        "        'password': 'raw-password',\n"
        "        'nested': {'authorization': 'Bearer raw-bearer', 'safe': 'ok'},\n"
        "    }]\n",
        encoding="utf-8",
    )

    result = cli(
        [
            "search",
            "python",
            "--site",
            "linkedin",
            "--location",
            "Remote",
            "--country",
            "USA",
            "--limit",
            "1",
            "--save",
        ],
        tmp_path,
        env_extra={"PYTHONPATH": f"{tmp_path}:{ROOT / 'src'}"},
    )

    assert result.returncode == 0
    combined = result.stdout + result.stderr
    for forbidden in ["stdout-secret", "url-secret", "raw-password", "raw-bearer"]:
        assert forbidden not in combined
    assert "token=" not in combined

    database = tmp_path / "state" / "jobloom" / "jobs.sqlite3"
    with sqlite3.connect(database) as conn:
        raw_json = conn.execute("SELECT raw_json FROM jobs").fetchone()[0]
    for forbidden in ["token", "password", "authorization", "url-secret", "raw-password"]:
        assert forbidden not in raw_json


def test_jobspy_cli_strips_sensitive_query_key_parts_from_output_and_sqlite(tmp_path):
    fake = tmp_path / "jobspy.py"
    fake.write_text(
        "def scrape_jobs(**kwargs):\n"
        "    return [{\n"
        "        'site': 'linkedin',\n"
        "        'id': 'query-parts',\n"
        "        'title': 'Engineer',\n"
        "        'job_url': 'https://example.com/jobs/1?session_id=s1&debug_secret=s2&auth_token=s3&keep=ok',\n"
        "        'apply_url': 'https://example.com/apply?user_password=s4&Cookie_Value=s5&credential_ref=s6&ok=1',\n"
        "        'raw_apply': 'https://example.com/raw?Debug_Secret=s7&safe=yes',\n"
        "    }]\n",
        encoding="utf-8",
    )

    result = cli(
        [
            "search",
            "python",
            "--site",
            "linkedin",
            "--location",
            "Remote",
            "--country",
            "USA",
            "--limit",
            "1",
            "--save",
        ],
        tmp_path,
        env_extra={"PYTHONPATH": f"{tmp_path}:{ROOT / 'src'}"},
    )

    assert result.returncode == 0
    combined = result.stdout + result.stderr
    for forbidden in ["s1", "s2", "s3", "s4", "s5", "s6", "s7"]:
        assert forbidden not in combined
    rows = json.loads(result.stdout)
    assert rows[0]["posting_url"] == "https://example.com/jobs/1?keep=ok"
    assert rows[0]["apply_url"] == "https://example.com/apply?ok=1"
    assert rows[0]["raw"]["raw_apply"] == "https://example.com/raw?safe=yes"

    database = tmp_path / "state" / "jobloom" / "jobs.sqlite3"
    with sqlite3.connect(database) as conn:
        raw_json = conn.execute("SELECT raw_json FROM jobs").fetchone()[0]
    for forbidden in ["s1", "s2", "s3", "s4", "s5", "s6", "s7"]:
        assert forbidden not in raw_json
    assert "keep=ok" in raw_json
    assert "ok=1" in raw_json
    assert "safe=yes" in raw_json


def test_jobspy_failure_redacts_exception_values_in_structured_stderr(tmp_path):
    fake = tmp_path / "jobspy.py"
    fake.write_text(
        "def scrape_jobs(**kwargs):\n"
        "    raise RuntimeError('token=token-secret password=password-secret cookie=cookie-secret Bearer bearer-secret')\n",
        encoding="utf-8",
    )

    result = cli(
        ["search", "python", "--location", "Remote", "--country", "USA", "--format", "table"],
        tmp_path,
        env_extra={"PYTHONPATH": f"{tmp_path}:{ROOT / 'src'}"},
    )

    assert result.returncode == 6
    assert result.stdout == ""
    error = json.loads(result.stderr)["error"]
    assert error["code"] == "jobspy_search_failed"
    for forbidden in ["token-secret", "password-secret", "cookie-secret", "bearer-secret"]:
        assert forbidden not in result.stderr


def test_jobspy_failure_strips_sensitive_query_key_parts_from_exception_url(tmp_path):
    fake = tmp_path / "jobspy.py"
    fake.write_text(
        "def scrape_jobs(**kwargs):\n"
        "    raise RuntimeError(\n"
        "        'failed at https://example.com/jobs?session_id=s1&debug_secret=s2&Auth_Token=s3&user_password=s4&cookie_value=s5&credential_ref=s6&keep=ok'\n"
        "    )\n",
        encoding="utf-8",
    )

    result = cli(
        ["search", "python", "--location", "Remote", "--country", "USA"],
        tmp_path,
        env_extra={"PYTHONPATH": f"{tmp_path}:{ROOT / 'src'}"},
    )

    assert result.returncode == 6
    assert result.stdout == ""
    error = json.loads(result.stderr)["error"]
    assert error["code"] == "jobspy_search_failed"
    for forbidden in ["s1", "s2", "s3", "s4", "s5", "s6"]:
        assert forbidden not in result.stderr
    assert "https://example.com/jobs?keep=ok" in error["message"]
