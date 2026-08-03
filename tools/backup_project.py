"""Создаёт проверенную резервную копию только публичного Git-источника."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


PROJECT_NAME = "ai-accounting-digest"
STATE_FILENAME = ".backup-state.json"


def run(command: list[str], *, cwd: Path) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout.strip()


def git(git_executable: str, repo: Path, *arguments: str) -> str:
    return run(
        [git_executable, "-c", "http.sslBackend=openssl", *arguments],
        cwd=repo,
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_remote_url(url: str) -> str:
    """Удаляет возможные учётные данные из URL перед записью в манифест."""
    if "://" not in url:
        sanitized = url.split("?", 1)[0].split("#", 1)[0]
        if re.match(r"^[^/\\]+@[^:]+:.+$", sanitized):
            sanitized = sanitized.split("@", 1)[1]
        return sanitized
    parts = urlsplit(url)
    host = parts.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, "", ""))


def assert_safe_locations(repo: Path, destination: Path) -> None:
    if not (repo / ".git").exists():
        raise ValueError(f"Не найден Git-репозиторий: {repo}")
    try:
        destination.relative_to(repo)
    except ValueError:
        return
    raise ValueError("Папка резервных копий не может находиться внутри репозитория")


def read_state(destination: Path) -> dict[str, str]:
    path = destination / STATE_FILENAME
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def write_state(destination: Path, state: dict[str, str]) -> None:
    temporary = destination / f"{STATE_FILENAME}.tmp"
    temporary.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination / STATE_FILENAME)


def verify_package(package: Path, *, git_executable: str, repo: Path) -> None:
    manifest_path = package / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    checksum_path = package / "SHA256SUMS.txt"

    expected: dict[str, str] = {}
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        checksum, filename = line.split("  ", 1)
        expected[filename] = checksum

    for filename, checksum in expected.items():
        path = package / filename
        if not path.is_file() or sha256(path) != checksum:
            raise RuntimeError(f"Не совпала контрольная сумма: {filename}")

    bundle = package / manifest["files"]["bundle"]
    git(git_executable, repo, "bundle", "verify", str(bundle))

    snapshot = package / manifest["files"]["snapshot"]
    with zipfile.ZipFile(snapshot) as archive:
        broken = archive.testzip()
    if broken:
        raise RuntimeError(f"Повреждён файл внутри ZIP: {broken}")


def create_backup(
    *,
    repo: Path,
    destination: Path,
    git_executable: str,
    remote: str = "origin",
    branch: str = "main",
    force: bool = False,
    now: datetime | None = None,
) -> dict[str, str]:
    repo = repo.resolve()
    destination = destination.resolve()
    assert_safe_locations(repo, destination)
    destination.mkdir(parents=True, exist_ok=True)

    git(git_executable, repo, "fetch", "--prune", remote, branch)

    ref = f"refs/remotes/{remote}/{branch}"
    commit_sha = git(git_executable, repo, "rev-parse", "--verify", ref)
    if not re.fullmatch(r"[0-9a-f]{40,64}", commit_sha):
        raise RuntimeError("Git вернул неожиданный идентификатор коммита")

    state = read_state(destination)
    if not force and state.get("last_commit_sha") == commit_sha:
        return {
            "status": "unchanged",
            "commit_sha": commit_sha,
            "archive_directory": state.get("archive_directory", ""),
        }

    created_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    short_sha = commit_sha[:7]
    folder_name = f"{created_at:%Y-%m-%d_%H%M%S}_{short_sha}"
    final_directory = destination / f"{created_at:%Y}" / f"{created_at:%m}" / folder_name
    if final_directory.exists():
        verify_package(final_directory, git_executable=git_executable, repo=repo)
        write_state(
            destination,
            {
                "last_commit_sha": commit_sha,
                "archive_directory": str(final_directory),
                "verified_at_utc": created_at.isoformat(),
            },
        )
        return {
            "status": "existing_verified",
            "commit_sha": commit_sha,
            "archive_directory": str(final_directory),
        }

    remote_url = safe_remote_url(git(git_executable, repo, "remote", "get-url", remote))
    commit_time = git(git_executable, repo, "show", "-s", "--format=%cI", commit_sha)
    bundle_name = f"{PROJECT_NAME}_{short_sha}.bundle"
    snapshot_name = f"{PROJECT_NAME}_{short_sha}.zip"

    with tempfile.TemporaryDirectory(prefix=f"{PROJECT_NAME}-backup-") as temporary:
        staging = Path(temporary)
        bundle_path = staging / bundle_name
        snapshot_path = staging / snapshot_name

        git(git_executable, repo, "bundle", "create", str(bundle_path), ref)
        git(
            git_executable,
            repo,
            "archive",
            "--format=zip",
            f"--output={snapshot_path}",
            commit_sha,
        )

        manifest = {
            "schema_version": 1,
            "project": PROJECT_NAME,
            "created_at_utc": created_at.isoformat(),
            "source_remote": remote_url,
            "source_ref": ref,
            "branch": branch,
            "commit_sha": commit_sha,
            "commit_time": commit_time,
            "scope": "public_origin_main_only",
            "files": {
                "bundle": bundle_name,
                "snapshot": snapshot_name,
                "restore_guide": "КАК_ВОССТАНОВИТЬ.md",
            },
        }
        (staging / "MANIFEST.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (staging / "КАК_ВОССТАНОВИТЬ.md").write_text(
            "# Восстановление проекта\n\n"
            f"Коммит: `{commit_sha}`.\n\n"
            "Самый простой вариант — распаковать ZIP-снимок. Чтобы восстановить "
            "Git-историю, выполните из папки с архивом:\n\n"
            "```powershell\n"
            "git init restored-project\n"
            "git -C restored-project fetch ../"
            f"{bundle_name} {ref}:refs/heads/main\n"
            "git -C restored-project checkout main\n"
            "```\n\n"
            "После восстановления запустите `python tools/restore_backup.py "
            "<папка-архива> --restore-to <новая-папка>`.\n",
            encoding="utf-8",
        )

        checksummed = [
            bundle_name,
            snapshot_name,
            "MANIFEST.json",
            "КАК_ВОССТАНОВИТЬ.md",
        ]
        checksum_text = "".join(
            f"{sha256(staging / filename)}  {filename}\n"
            for filename in checksummed
        )
        (staging / "SHA256SUMS.txt").write_text(checksum_text, encoding="utf-8")
        verify_package(staging, git_executable=git_executable, repo=repo)

        pending = final_directory.with_name(final_directory.name + ".partial")
        if pending.exists():
            raise RuntimeError(f"Осталась незавершённая копия: {pending}")
        pending.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(staging, pending)
        verify_package(pending, git_executable=git_executable, repo=repo)
        pending.rename(final_directory)

    state = {
        "last_commit_sha": commit_sha,
        "archive_directory": str(final_directory),
        "verified_at_utc": created_at.isoformat(),
    }
    write_state(destination, state)
    return {
        "status": "created",
        "commit_sha": commit_sha,
        "archive_directory": str(final_directory),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--git", dest="git_executable", default=os.environ.get("GIT_EXECUTABLE", "git"))
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--force", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = create_backup(
            repo=args.repo,
            destination=args.destination,
            git_executable=args.git_executable,
            remote=args.remote,
            branch=args.branch,
            force=args.force,
        )
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=True))
        return 1

    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
