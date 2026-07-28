from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path

from jobloom import release_check


def test_skill_frontmatter_at_byte_zero():
    data = Path("SKILL.md").read_bytes()
    assert data.startswith(b"---\nname: jobloom")
    text = data.decode("utf-8")
    assert "metadata:\n  hermes:\n    tags:" in text


def test_required_project_files_exist():
    for path in [
        "README.md",
        "LICENSE",
        "SECURITY.md",
        "CONTRIBUTING.md",
        "CHANGELOG.md",
        "docs/providers.md",
        "examples/config.toml",
        ".github/workflows/ci.yml",
        ".github/dependabot.yml",
    ]:
        assert Path(path).exists()


def test_public_files_do_not_contain_private_paths_or_secret_patterns():
    release_check.scan_public_files(Path.cwd())


def test_release_check_rejects_generic_cookie_assignment_and_colon_forms():
    for data in [
        b"cookie=fake-cookie",
        b"cookie: fake-cookie",
        b"Authorization: fake-token",
        b"passwd = fake-pass",
    ]:
        try:
            release_check.scan_bytes("fixture", data, secrets=True)
        except SystemExit as exc:
            assert "obvious secret pattern" in str(exc)
        else:
            raise AssertionError(f"secret pattern was not rejected: {data!r}")


def test_archive_scanner_inspects_contents_and_rejects_private_paths(tmp_path):
    wheel = tmp_path / "jobloom-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("jobloom/cli.py", "print('ok')")
        private_path = "/opt" + "/data/config.yaml"
        archive.writestr("jobloom/release_check.py", f"PRIVATE={private_path!r}")
    try:
        release_check.scan_wheel(wheel)
    except SystemExit as exc:
        assert "private absolute path" in str(exc)
    else:
        raise AssertionError("private path in wheel was not rejected")


def test_archive_scanner_rejects_secret_assignment_in_wheel_code(tmp_path):
    wheel = tmp_path / "jobloom-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("jobloom/cli.py", "PASSWORD = 'wheel-secret'\n")
        archive.writestr("jobloom/release_check.py", "print('ok')\n")
    try:
        release_check.scan_wheel(wheel)
    except SystemExit as exc:
        assert "obvious secret pattern" in str(exc)
    else:
        raise AssertionError("secret assignment in wheel code was not rejected")


def test_archive_scanner_requires_expected_sdist_members(tmp_path):
    sdist = tmp_path / "jobloom-0.1.0.tar.gz"
    source = tmp_path / "README.md"
    source.write_text("# ok\n", encoding="utf-8")
    with tarfile.open(sdist, "w:gz") as archive:
        archive.add(source, arcname="jobloom-0.1.0/README.md")
    try:
        release_check.scan_sdist(sdist)
    except SystemExit as exc:
        assert "missing LICENSE" in str(exc)
    else:
        raise AssertionError("incomplete sdist was not rejected")


def test_archive_scanner_rejects_secret_assignment_in_sdist_src(tmp_path):
    sdist = tmp_path / "jobloom-0.1.0.tar.gz"
    files = {
        "jobloom-0.1.0/README.md": "# ok\n",
        "jobloom-0.1.0/LICENSE": "ok\n",
        "jobloom-0.1.0/SKILL.md": "ok\n",
        "jobloom-0.1.0/scripts/release-check.sh": "#!/usr/bin/env bash\n",
        "jobloom-0.1.0/src/jobloom/cli.py": "token = 'sdist-secret'\n",
        "jobloom-0.1.0/tests/fixtures.py": "token = 'allowed-fake-fixture'\n",
    }
    with tarfile.open(sdist, "w:gz") as archive:
        for name, text in files.items():
            source = tmp_path / name.replace("/", "_")
            source.write_text(text, encoding="utf-8")
            archive.add(source, arcname=name)
    try:
        release_check.scan_sdist(sdist)
    except SystemExit as exc:
        assert "obvious secret pattern" in str(exc)
        assert "src/jobloom/cli.py" in str(exc)
    else:
        raise AssertionError("secret assignment in sdist src was not rejected")


def test_release_check_script_exists():
    script = Path("scripts/release-check.sh")
    assert script.exists()
    assert script.stat().st_mode & 0o111
