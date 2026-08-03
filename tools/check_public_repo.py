"""Проверяет, что в публичный репозиторий не попали опасные файлы и строки."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


MAX_FILE_SIZE = 5 * 1024 * 1024
FORBIDDEN_DIRECTORY_NAMES = {
    ".backup",
    "backups",
    "internal",
    "private",
    "secrets",
}
FORBIDDEN_FILENAMES = {
    ".env",
    "credentials.json",
    "requests.csv",
    "service-account.json",
}
FORBIDDEN_SUFFIXES = {
    ".7z",
    ".bundle",
    ".gz",
    ".key",
    ".p12",
    ".pem",
    ".pfx",
    ".rar",
    ".tar",
    ".zip",
}
KNOWN_BINARY_SUFFIXES = {
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".pdf",
    ".png",
    ".webp",
}

USER_PATH_PATTERN = re.compile(
    r"(?i)(?:[A-Z]:[\\/]" + "Users" + r"[\\/](?!\.{3}|<)[^\\/\r\n]+[\\/]"
    + "|/" + "Users" + r"/(?!\.{3}|<)[^/\r\n]+/"
    + "|/" + "home" + r"/(?!\.{3}|<)[^/\r\n]+/)"
)

SENSITIVE_PATTERNS = (
    (
        USER_PATH_PATTERN,
        "абсолютный пользовательский путь",
    ),
    (
        re.compile("-----" + r"BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
        "закрытый ключ",
    ),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), "токен GitHub"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), "токен GitHub"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"), "ключ Google API"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "ключ AWS"),
    (
        re.compile(
            r"(?i)\b(?:api[_-]?key|password|secret|token)\s*[:=]\s*"
            r"['\"][^'\"\s]{8,}['\"]"
        ),
        "похожее на секрет значение",
    ),
)


def tracked_files(root: Path) -> list[Path]:
    """Возвращает отслеживаемые и новые неигнорируемые файлы."""
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return [root / item for item in result.stdout.decode("utf-8").split("\0") if item]


def validate_file(root: Path, path: Path) -> list[str]:
    relative = path.relative_to(root)
    relative_text = relative.as_posix()
    parts = {part.casefold() for part in relative.parts[:-1]}
    filename = relative.name.casefold()
    suffix = relative.suffix.casefold()
    errors: list[str] = []

    forbidden_parts = parts & FORBIDDEN_DIRECTORY_NAMES
    if forbidden_parts:
        errors.append(
            f"{relative_text}: запрещённая папка {sorted(forbidden_parts)[0]}"
        )

    if filename in FORBIDDEN_FILENAMES or (
        filename.startswith(".env.") and filename != ".env.example"
    ):
        errors.append(f"{relative_text}: запрещённое имя файла")

    if suffix in FORBIDDEN_SUFFIXES:
        errors.append(f"{relative_text}: запрещённый тип файла {suffix}")

    if not path.exists():
        errors.append(f"{relative_text}: отслеживаемый файл отсутствует")
        return errors

    if path.stat().st_size > MAX_FILE_SIZE:
        errors.append(f"{relative_text}: файл больше 5 МБ")

    if suffix in KNOWN_BINARY_SUFFIXES:
        return errors

    raw = path.read_bytes()
    if b"\0" in raw:
        errors.append(f"{relative_text}: неожиданный бинарный файл")
        return errors

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        errors.append(f"{relative_text}: текстовый файл не в UTF-8")
        return errors

    for pattern, description in SENSITIVE_PATTERNS:
        match = pattern.search(text)
        if match:
            line = text.count("\n", 0, match.start()) + 1
            errors.append(f"{relative_text}:{line}: найден {description}")

    return errors


def validate_paths(root: Path, paths: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in paths:
        errors.extend(validate_file(root, path))
    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    try:
        paths = tracked_files(root)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Не удалось получить список файлов Git: {exc}", file=sys.stderr)
        return 2

    errors = validate_paths(root, paths)
    if errors:
        print("Публичная проверка не пройдена:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"Публичная проверка пройдена: {len(paths)} файлов.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
