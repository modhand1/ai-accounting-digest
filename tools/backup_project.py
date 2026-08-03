"""Создаёт проверенную резервную копию только публичного Git-источника."""

from __future__ import annotations

import argparse
import configparser
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


def git_environment() -> dict[str, str]:
    """Не позволяет внешним Git-конфигам менять поведение резервной копии."""
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("GIT_")
    }
    environment.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": "",
            "SSH_ASKPASS": "",
        }
    )
    return environment


def run(command: list[str], *, cwd: Path) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=git_environment(),
    )
    return result.stdout.strip()


def git_command(git_executable: str, *arguments: str) -> list[str]:
    """Собирает автономную команду Git без обращения к хранилищу учётных данных."""
    command = [git_executable]
    executable = Path(git_executable)
    if executable.is_file():
        helper_candidates = (
            executable.parent,
            executable.parent.parent / "mingw64" / "bin",
        )
        for candidate in helper_candidates:
            if (candidate / "git-remote-https.exe").is_file():
                command.append(f"--exec-path={candidate}")
                break
    command.extend(
        [
            "-c",
            "http.sslBackend=openssl",
            "-c",
            "credential.helper=",
            *arguments,
        ]
    )
    return command


def git(git_executable: str, repo: Path, *arguments: str) -> str:
    return run(git_command(git_executable, *arguments), cwd=repo)


def validate_ref_name(value: str, *, label: str) -> str:
    if (
        not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", value)
        or ".." in value
        or "//" in value
        or "@{" in value
        or value.endswith(("/", "."))
    ):
        raise ValueError(f"Некорректное имя {label}: {value}")
    return value


def read_public_remote_url(repo: Path, remote: str) -> str:
    """Читает только URL из локального конфига, не запуская Git в чужой папке."""
    remote = validate_ref_name(remote, label="remote")
    config_path = repo / ".git" / "config"
    if not config_path.is_file():
        raise ValueError(f"Не найден Git-конфиг: {config_path}")

    parser = configparser.RawConfigParser(interpolation=None, strict=False)
    try:
        with config_path.open("r", encoding="utf-8") as source:
            parser.read_file(source)
    except (OSError, configparser.Error) as exc:
        raise ValueError("Не удалось безопасно прочитать Git-конфиг") from exc

    section = f'remote "{remote}"'
    url = parser.get(section, "url", fallback="").strip()
    if not url or any(character in url for character in "\r\n\0"):
        raise ValueError(f"Не найден безопасный URL remote {remote}")

    if re.match(r"^[A-Za-z]:[\\/]", url) or url.startswith(("/", "\\\\")):
        local_path = Path(url).resolve()
        if not local_path.exists():
            raise ValueError("Локальный Git-источник не существует")
        return str(local_path)

    parts = urlsplit(url)
    if parts.scheme == "file":
        if parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError("Локальный Git URL содержит лишние данные")
        return url
    if parts.scheme != "https" or not parts.hostname:
        raise ValueError("Для резервной копии разрешён только публичный HTTPS remote")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("Remote URL не должен содержать учётные данные или параметры")
    return url


def create_trusted_repository(git_executable: str, root: Path) -> Path:
    trusted_repo = root / "trusted.git"
    run(
        git_command(git_executable, "init", "--bare", str(trusted_repo)),
        cwd=root,
    )
    return trusted_repo


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
    branch = validate_ref_name(branch, label="branch")
    remote = validate_ref_name(remote, label="remote")
    remote_url = read_public_remote_url(repo, remote)
    destination.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix=f"{PROJECT_NAME}-backup-") as temporary:
        temporary_root = Path(temporary)
        trusted_repo = create_trusted_repository(git_executable, temporary_root)
        ref = f"refs/remotes/{remote}/{branch}"
        git(
            git_executable,
            trusted_repo,
            "fetch",
            "--prune",
            remote_url,
            f"+refs/heads/{branch}:{ref}",
        )

        commit_sha = git(git_executable, trusted_repo, "rev-parse", "--verify", ref)
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
            verify_package(final_directory, git_executable=git_executable, repo=trusted_repo)
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

        commit_time = git(git_executable, trusted_repo, "show", "-s", "--format=%cI", commit_sha)
        bundle_name = f"{PROJECT_NAME}_{short_sha}.bundle"
        snapshot_name = f"{PROJECT_NAME}_{short_sha}.zip"
        staging = temporary_root / "package"
        staging.mkdir()
        bundle_path = staging / bundle_name
        snapshot_path = staging / snapshot_name

        git(git_executable, trusted_repo, "bundle", "create", str(bundle_path), ref)
        git(
            git_executable,
            trusted_repo,
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
        verify_package(staging, git_executable=git_executable, repo=trusted_repo)

        pending = final_directory.with_name(final_directory.name + ".partial")
        if pending.exists():
            raise RuntimeError(f"Осталась незавершённая копия: {pending}")
        pending.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(staging, pending)
        verify_package(pending, git_executable=git_executable, repo=trusted_repo)
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
