"""Проверяет резервный комплект и при необходимости восстанавливает проект."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import zipfile
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def verify_checksums(archive_directory: Path) -> None:
    checksum_file = archive_directory / "SHA256SUMS.txt"
    for line in checksum_file.read_text(encoding="utf-8").splitlines():
        checksum, filename = line.split("  ", 1)
        path = archive_directory / filename
        if not path.is_file() or sha256(path) != checksum:
            raise RuntimeError(f"Не совпала контрольная сумма: {filename}")


def verify_archive(
    archive_directory: Path,
    *,
    git_executable: str = "git",
    restore_to: Path | None = None,
) -> dict[str, str]:
    archive_directory = archive_directory.resolve()
    manifest = json.loads(
        (archive_directory / "MANIFEST.json").read_text(encoding="utf-8")
    )
    verify_checksums(archive_directory)

    snapshot = archive_directory / manifest["files"]["snapshot"]
    with zipfile.ZipFile(snapshot) as zip_file:
        broken = zip_file.testzip()
    if broken:
        raise RuntimeError(f"Повреждён файл внутри ZIP: {broken}")

    requested_restore = restore_to.resolve() if restore_to else None
    if requested_restore and requested_restore.exists() and any(requested_restore.iterdir()):
        raise ValueError("Папка восстановления уже существует и не пуста")

    with tempfile.TemporaryDirectory(prefix="backup-restore-check-") as temporary:
        target = requested_restore or Path(temporary) / "restored-project"
        target.mkdir(parents=True, exist_ok=True)
        run([git_executable, "init", str(target)], cwd=archive_directory)
        bundle = archive_directory / manifest["files"]["bundle"]
        run(
            [
                git_executable,
                "-C",
                str(target),
                "fetch",
                str(bundle),
                f"{manifest['source_ref']}:refs/heads/main",
            ],
            cwd=archive_directory,
        )
        restored_sha = run(
            [git_executable, "-C", str(target), "rev-parse", "main"],
            cwd=archive_directory,
        )
        if restored_sha != manifest["commit_sha"]:
            raise RuntimeError("Восстановленный коммит не совпадает с манифестом")
        if requested_restore:
            run(
                [git_executable, "-C", str(target), "checkout", "main"],
                cwd=archive_directory,
            )

    return {
        "status": "verified",
        "commit_sha": manifest["commit_sha"],
        "archive_directory": str(archive_directory),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive_directory", type=Path)
    parser.add_argument("--restore-to", type=Path)
    parser.add_argument("--git", dest="git_executable", default=os.environ.get("GIT_EXECUTABLE", "git"))
    args = parser.parse_args()

    try:
        result = verify_archive(
            args.archive_directory,
            git_executable=args.git_executable,
            restore_to=args.restore_to,
        )
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=True))
        return 1

    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
