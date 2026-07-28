from __future__ import annotations

import re
import sys
import tarfile
import zipfile
from pathlib import Path

PUBLIC_FILES = [
    "README.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "SKILL.md",
    "docs/providers.md",
    "examples/config.toml",
    ".github/workflows/ci.yml",
    ".github/dependabot.yml",
    "pyproject.toml",
]

PRIVATE_PATH = re.compile(rb"/(?:opt|home|Users)/[^\s'\")<>]+")
SECRET_PATTERN = re.compile(
    rb"(?i)(Bearer\s+[A-Za-z0-9._~+/=-]+|\b(?:password|passwd|token|secret|credential|session|cookie|authorization|li_at|jsessionid)\b\s*(?:=|:)\s*['\"]?[A-Za-z0-9][^'\";\s,&}\]\[]*)"
)


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    if len(args) != 2:
        print("usage: python -m jobloom.release_check DIST_DIR public-files", file=sys.stderr)
        return 2
    dist_dir = Path(args[0])
    scan_archives(dist_dir)
    scan_public_files(Path.cwd())
    return 0


def scan_archives(dist_dir: Path) -> None:
    archives = sorted(dist_dir.glob("jobloom-0.1.0*"))
    if not archives:
        raise SystemExit("no jobloom 0.1.0 archives found")
    for archive in archives:
        if archive.suffix == ".whl":
            scan_wheel(archive)
        elif archive.name.endswith(".tar.gz"):
            scan_sdist(archive)


def scan_wheel(path: Path) -> None:
    with zipfile.ZipFile(path) as wheel:
        names = wheel.namelist()
        require_archive_members(path, names, ["jobloom/cli.py", "jobloom/release_check.py"])
        for name in names:
            scan_bytes(f"{path}:{name}", wheel.read(name), secrets=is_wheel_code_member(name))


def scan_sdist(path: Path) -> None:
    with tarfile.open(path, "r:gz") as sdist:
        members = [member for member in sdist.getmembers() if member.isfile()]
        names = [member.name for member in members]
        require_archive_members(
            path, names, ["README.md", "LICENSE", "SKILL.md", "scripts/release-check.sh"]
        )
        for member in members:
            extracted = sdist.extractfile(member)
            if extracted is not None:
                scan_bytes(
                    f"{path}:{member.name}",
                    extracted.read(),
                    secrets=is_sdist_secret_member(member.name),
                )


def require_archive_members(path: Path, names: list[str], required_suffixes: list[str]) -> None:
    for suffix in required_suffixes:
        if not any(name.endswith(suffix) for name in names):
            raise SystemExit(f"{path} missing {suffix}")


def scan_public_files(root: Path) -> None:
    for relative in PUBLIC_FILES:
        scan_bytes(relative, (root / relative).read_bytes(), secrets=True)


def is_public_archive_member(name: str) -> bool:
    return any(name.endswith(f"/{relative}") or name == relative for relative in PUBLIC_FILES)


def is_wheel_code_member(name: str) -> bool:
    return name.startswith("jobloom/") and name.endswith(".py")


def is_sdist_secret_member(name: str) -> bool:
    return is_public_archive_member(name) or "/src/" in name


def scan_bytes(label: str, data: bytes, *, secrets: bool) -> None:
    if PRIVATE_PATH.search(data):
        raise SystemExit(f"private absolute path found in {label}")
    if secrets and SECRET_PATTERN.search(data):
        raise SystemExit(f"obvious secret pattern found in {label}")


if __name__ == "__main__":
    raise SystemExit(main())
