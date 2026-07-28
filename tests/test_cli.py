from __future__ import annotations

import json
import os
import stat

from conftest import cli


def test_version_and_help(tmp_path):
    version = cli(["--version"], tmp_path)
    assert version.returncode == 0
    assert version.stdout.strip() == "jobloom 0.1.0"
    assert version.stderr == ""

    help_result = cli(["--help"], tmp_path)
    assert help_result.returncode == 0
    assert "search" in help_result.stdout


def test_usage_error_is_structured(tmp_path):
    result = cli(["search", "python"], tmp_path)
    assert result.returncode == 2
    assert result.stdout == ""
    assert len(result.stderr.splitlines()) == 1
    assert json.loads(result.stderr)["error"]["code"] == "usage"
    assert "usage:" not in result.stderr


def test_init_permissions_and_no_overwrite(tmp_path):
    result = cli(["init"], tmp_path)
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    config_file = tmp_path / "config" / "jobloom" / "config.toml"
    state_dir = tmp_path / "state" / "jobloom"
    assert payload["config_file"] == str(config_file)
    assert stat.S_IMODE(config_file.stat().st_mode) == 0o600
    assert stat.S_IMODE(state_dir.stat().st_mode) == 0o700

    second = cli(["init"], tmp_path)
    assert second.returncode == 3
    assert json.loads(second.stderr)["error"]["code"] == "config_exists"


def test_init_rejects_symlink_config(tmp_path):
    cfg_dir = tmp_path / "config" / "jobloom"
    cfg_dir.mkdir(parents=True)
    target = tmp_path / "elsewhere"
    (cfg_dir / "config.toml").symlink_to(target)
    result = cli(["init", "--force"], tmp_path)
    assert result.returncode == 3
    assert json.loads(result.stderr)["error"]["code"] == "config_error"


def test_provider_config_read_rejects_symlink_config_without_traceback(tmp_path):
    cfg_dir = tmp_path / "config" / "jobloom"
    cfg_dir.mkdir(parents=True)
    target = tmp_path / "missing-config.toml"
    (cfg_dir / "config.toml").symlink_to(target)
    result = cli(["feed", "linkedin"], tmp_path)
    assert result.returncode == 3
    assert json.loads(result.stderr)["error"]["code"] == "config_error"
    assert "Traceback" not in result.stderr


def test_doctor_and_providers_are_offline(tmp_path):
    doctor = cli(["doctor"], tmp_path)
    assert doctor.returncode == 0
    assert json.loads(doctor.stdout)["linked_executable"]["available"] is False

    providers = cli(["providers"], tmp_path)
    assert providers.returncode == 0
    rows = json.loads(providers.stdout)
    assert [row["name"] for row in rows] == ["jobspy-public", "linkedin-linked", "indeed-native"]


def test_table_output_has_expected_headers_and_data(tmp_path):
    init = cli(["init", "--format", "table"], tmp_path)
    assert init.returncode == 0
    assert "config_file" in init.stdout
    assert "created" in init.stdout

    doctor = cli(["doctor", "--format", "table"], tmp_path)
    assert doctor.returncode == 0
    assert "linked_executable" in doctor.stdout
    assert "available" in doctor.stdout

    providers = cli(["providers", "--format", "table"], tmp_path)
    assert providers.returncode == 0
    assert "name" in providers.stdout
    assert "jobspy-public" in providers.stdout

    duplicate_init = cli(["init", "--format", "table"], tmp_path)
    assert duplicate_init.returncode == 3
    assert duplicate_init.stdout == ""
    assert json.loads(duplicate_init.stderr)["error"]["code"] == "config_exists"
    assert not duplicate_init.stderr.startswith("error:")


def test_init_directory_oserror_is_structured(tmp_path):
    blocked = tmp_path / "blocked"
    blocked.write_text("not a dir", encoding="utf-8")
    result = cli(["init"], tmp_path, env_extra={"XDG_CONFIG_HOME": str(blocked)})
    assert result.returncode == 3
    assert json.loads(result.stderr)["error"]["code"] == "config_error"
    assert "Traceback" not in result.stderr


def test_init_creates_config_with_private_initial_mode(tmp_path):
    result = cli(["init"], tmp_path)
    assert result.returncode == 0
    config_file = tmp_path / "config" / "jobloom" / "config.toml"
    assert stat.S_IMODE(os.stat(config_file).st_mode) == 0o600


def test_indeed_feed_explicit_unavailable(tmp_path):
    result = cli(["feed", "indeed"], tmp_path)
    assert result.returncode == 4
    assert result.stdout == ""
    error = json.loads(result.stderr)["error"]
    assert error["code"] == "provider_unavailable"
    assert "not Indeed For You" in error["hint"]
