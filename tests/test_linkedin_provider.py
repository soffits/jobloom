from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from conftest import cli


def write_config(tmp_path: Path, executable: str | None, timeout: object = 5) -> None:
    cfg_dir = tmp_path / "config" / "jobloom"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    executable_line = f"executable = {json.dumps(executable)}\n" if executable is not None else ""
    timeout_value = json.dumps(timeout) if isinstance(timeout, str | bool) else str(timeout)
    (cfg_dir / "config.toml").write_text(
        f"[providers.linkedin_linked]\n{executable_line}timeout_seconds = {timeout_value}\n",
        encoding="utf-8",
    )


def make_exe(tmp_path: Path, body: str) -> Path:
    exe = tmp_path / "linked-fake"
    exe.write_text(body, encoding="utf-8")
    exe.chmod(0o700)
    return exe


def test_linkedin_fake_success_and_save(tmp_path):
    exe = make_exe(
        tmp_path,
        '#!/bin/sh\nprintf \'%s\' \'{"items":[{"id":"1","title":"Role","company":"Acme","url":"https://www.linkedin.com/jobs/view/1/?trk=x"}]}\'\n',
    )
    write_config(tmp_path, str(exe))
    result = cli(["feed", "linkedin", "--limit", "1", "--save"], tmp_path)
    assert result.returncode == 0
    rows = json.loads(result.stdout)
    assert rows[0]["source"] == "linkedin-linked"
    assert rows[0]["source_kind"] == "platform_native_feed"
    assert rows[0]["canonical_url"] == "https://linkedin.com/jobs/view/1"

    listed = cli(["jobs", "list", "--source", "linkedin-linked"], tmp_path)
    assert len(json.loads(listed.stdout)) == 1


def test_linkedin_realistic_nested_fixture_synthesizes_url_and_saves(tmp_path):
    exe = make_exe(
        tmp_path,
        "#!/bin/sh\n"
        'printf \'%s\' \'{"items":[{"id":12345,"jobTitle":"Staff Engineer","company":{"name":"Acme"},"location":{"name":"Remote"},"postedAt":"2024-01-02T03:04:05Z"}]}\'\n',
    )
    write_config(tmp_path, str(exe))
    result = cli(["feed", "linkedin", "--limit", "1", "--save"], tmp_path)
    assert result.returncode == 0
    rows = json.loads(result.stdout)
    assert rows[0]["company"] == "Acme"
    assert rows[0]["location"] == "Remote"
    assert rows[0]["canonical_url"] == "https://linkedin.com/jobs/view/12345"
    assert rows[0]["posted_at"] == "2024-01-02T03:04:05Z"


def test_linkedin_missing_executable(tmp_path):
    write_config(tmp_path, str(tmp_path / "missing"))
    result = cli(["feed", "linkedin"], tmp_path)
    assert result.returncode == 4
    assert json.loads(result.stderr)["error"]["code"] == "provider_unavailable"


def test_linkedin_timeout(tmp_path):
    exe = make_exe(tmp_path, "#!/bin/sh\nsleep 2\n")
    write_config(tmp_path, str(exe), timeout=1)
    result = cli(["feed", "linkedin"], tmp_path)
    assert result.returncode == 4
    assert json.loads(result.stderr)["error"]["code"] == "provider_timeout"


def test_linkedin_nonzero_redacts_values_and_no_traceback(tmp_path):
    exe = make_exe(
        tmp_path,
        "#!/bin/sh\nprintf 'Authorization: Bearer fake-bearer-secret\\nCookie: li_at=fake-li; JSESSIONID=fake-jsession\\ntoken = fake-token\\npassword=fake-pass\\nsecret: fake-secret\\ncookie=fake-cookie\\n' >&2\nexit 7\n",
    )
    write_config(tmp_path, str(exe))
    result = cli(["feed", "linkedin"], tmp_path)
    assert result.returncode == 4
    assert "Traceback" not in result.stderr
    assert "fake-bearer-secret" not in result.stderr
    assert "fake-li" not in result.stderr
    assert "fake-jsession" not in result.stderr
    assert "fake-token" not in result.stderr
    assert "fake-pass" not in result.stderr
    assert "fake-secret" not in result.stderr
    assert "fake-cookie" not in result.stderr
    assert "token = [REDACTED]" in result.stderr
    assert "password=[REDACTED]" in result.stderr
    assert "secret: [REDACTED]" in result.stderr


def test_linkedin_malformed_and_drifted_json(tmp_path):
    bad = make_exe(tmp_path, "#!/bin/sh\nprintf 'not-json'\n")
    write_config(tmp_path, str(bad))
    malformed = cli(["feed", "linkedin"], tmp_path)
    assert json.loads(malformed.stderr)["error"]["code"] == "provider_output_drift"

    drift = make_exe(tmp_path, "#!/bin/sh\nprintf '%s' '{\"data\":{}}'\n")
    write_config(tmp_path, str(drift))
    drifted = cli(["feed", "linkedin"], tmp_path)
    assert json.loads(drifted.stderr)["error"]["code"] == "provider_output_drift"


def test_linkedin_non_object_items_and_bad_shapes_are_drift(tmp_path):
    exe = make_exe(tmp_path, "#!/bin/sh\nprintf '%s' '{\"items\":[1]}'\n")
    write_config(tmp_path, str(exe))
    result = cli(["feed", "linkedin"], tmp_path)
    assert result.returncode == 4
    assert json.loads(result.stderr)["error"]["code"] == "provider_output_drift"

    bad_shape = make_exe(tmp_path, '#!/bin/sh\nprintf \'%s\' \'{"items":[{"title":["bad"]}]}\'\n')
    write_config(tmp_path, str(bad_shape))
    result = cli(["feed", "linkedin"], tmp_path)
    assert result.returncode == 4
    assert json.loads(result.stderr)["error"]["code"] == "provider_output_drift"


def test_linkedin_sanitizes_stdout_secrets_from_output_and_sqlite(tmp_path):
    exe = make_exe(
        tmp_path,
        "#!/bin/sh\n"
        'printf \'%s\' \'{"items":[{"id":"9","title":"Role","url":"https://www.linkedin.com/jobs/view/9/?access_token=fake-query-secret","nested":{"password":"fake-password"},"note":"Authorization: Bearer fake-stdout-bearer","debug":"token = fake-token password=fake-pass secret: fake-secret cookie=fake-cookie"}]}\'\n',
    )
    write_config(tmp_path, str(exe))
    result = cli(["feed", "linkedin", "--limit", "1", "--save"], tmp_path)
    assert result.returncode == 0
    assert "fake-query-secret" not in result.stdout
    assert "fake-password" not in result.stdout
    assert "fake-stdout-bearer" not in result.stdout
    assert "fake-token" not in result.stdout
    assert "fake-pass" not in result.stdout
    assert "fake-secret" not in result.stdout
    assert "fake-cookie" not in result.stdout
    db = tmp_path / "state" / "jobloom" / "jobs.sqlite3"
    raw_json = sqlite3.connect(db).execute("SELECT raw_json FROM jobs").fetchone()[0]
    assert "fake-query-secret" not in raw_json
    assert "fake-password" not in raw_json
    assert "fake-stdout-bearer" not in raw_json
    assert "fake-token" not in raw_json
    assert "fake-pass" not in raw_json
    assert "fake-secret" not in raw_json
    assert "fake-cookie" not in raw_json


def test_linkedin_config_rejects_old_command_extra_argv_and_bad_timeout(tmp_path):
    cfg_dir = tmp_path / "config" / "jobloom"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    for body in [
        '[providers.linkedin_linked]\ncommand = ["linked", "--debug"]\n',
        '[providers.linkedin_linked]\nexecutable = ["linked"]\n',
        '[providers.linkedin_linked]\nexecutable = "linked"\ntimeout_seconds = true\n',
        '[providers.linkedin_linked]\nexecutable = "linked"\ntimeout_seconds = 0\n',
        '[providers.linkedin_linked]\nexecutable = "linked"\ntimeout_seconds = 301\n',
    ]:
        (cfg_dir / "config.toml").write_text(body, encoding="utf-8")
        result = cli(["feed", "linkedin"], tmp_path)
        assert result.returncode == 4
        assert json.loads(result.stderr)["error"]["code"] == "provider_config_invalid"


def test_linkedin_child_env_is_sanitized(tmp_path):
    exe = make_exe(
        tmp_path,
        '#!/bin/sh\nif [ -n "$LINKED_DEBUG" ]; then exit 8; fi\nif [ "$NO_COLOR" != 1 ]; then exit 9; fi\nprintf \'%s\' \'{"items":[]}\'\n',
    )
    write_config(tmp_path, str(exe))
    result = cli(["feed", "linkedin"], tmp_path, env_extra={"LINKED_DEBUG": "1"})
    assert result.returncode == 0


def test_shell_is_not_used():
    source = Path("src/jobloom/providers/linkedin_linked.py").read_text(encoding="utf-8")
    assert "shell=True" not in source
    assert "command," not in source
