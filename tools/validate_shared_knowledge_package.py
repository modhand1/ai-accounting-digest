"""Validate an exported Markdown knowledge package before upload."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REQUIRED_FIELDS = {
    "package_id", "corpus", "document_role", "status", "public_safe",
    "source", "canonical_source_type", "canonical_path", "date_exported",
    "freshness_sensitive",
}
DOCUMENT_ROLES = {
    "passport", "article", "project_rule", "research", "audit", "safety",
    "agent_reference",
}
SOURCE_TYPES = {"github", "local_project", "shared_base"}
ABSOLUTE_USER_PATH = re.compile(
    r"(?:[A-Za-z]:[\\/](?:Users|Documents and Settings)[\\/]|/Users/|/home/)",  # public-scan: allow
    re.IGNORECASE,
)
DATE_VALUE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def parse_frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("нет YAML frontmatter в начале файла")
    try:
        closing = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration as exc:
        raise ValueError("frontmatter не закрыт строкой ---") from exc

    metadata: dict[str, str] = {}
    for line_number, line in enumerate(lines[1:closing], start=2):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"строка {line_number}: ожидалось поле key: value")
        key, value = line.split(":", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"строка {line_number}: пустое имя поля")
        metadata[key] = unquote(value)
    return metadata


def is_true(value: str) -> bool:
    return value.strip().lower() == "true"


def is_false(value: str) -> bool:
    return value.strip().lower() == "false"


def validate_file(path: Path, allow_public_safe: bool = False) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    if ABSOLUTE_USER_PATH.search(text):
        errors.append("найден абсолютный пользовательский путь")

    try:
        metadata = parse_frontmatter(text)
    except ValueError as exc:
        return errors + [str(exc)]

    missing = sorted(REQUIRED_FIELDS - metadata.keys())
    if missing:
        errors.append("нет обязательных полей: " + ", ".join(missing))
    if metadata.get("corpus") != "website_knowledge":
        errors.append("corpus должен быть website_knowledge")

    role = metadata.get("document_role")
    if role and role not in DOCUMENT_ROLES:
        errors.append(f"неизвестный document_role: {role}")
    source_type = metadata.get("canonical_source_type")
    if source_type and source_type not in SOURCE_TYPES:
        errors.append(f"неизвестный canonical_source_type: {source_type}")

    canonical_path = metadata.get("canonical_path", "")
    if canonical_path and ABSOLUTE_USER_PATH.search(canonical_path):
        errors.append("canonical_path должен быть относительным путём или устойчивым ID")
    if source_type == "github" and not metadata.get("canonical_repository"):
        errors.append("для источника github требуется canonical_repository")

    if not allow_public_safe and not is_false(metadata.get("public_safe", "")):
        errors.append("public_safe должен оставаться false до отдельного решения владельца")

    freshness = metadata.get("freshness_sensitive", "")
    if not (is_true(freshness) or is_false(freshness)):
        errors.append("freshness_sensitive должен быть true или false")
    if is_true(freshness) and not DATE_VALUE.fullmatch(metadata.get("last_verified_at", "")):
        errors.append("для freshness_sensitive: true требуется last_verified_at в формате YYYY-MM-DD")
    if metadata.get("date_exported") and not DATE_VALUE.fullmatch(metadata["date_exported"]):
        errors.append("date_exported должен иметь формат YYYY-MM-DD")

    if role == "agent_reference":
        agent_fields = {
            "canonical_status", "automation_authority", "site_write_access",
            "publication_allowed",
        }
        missing_agent = sorted(agent_fields - metadata.keys())
        if missing_agent:
            errors.append("у справочной копии агента нет полей: " + ", ".join(missing_agent))
        for field in ("automation_authority", "site_write_access", "publication_allowed"):
            if field in metadata and not is_false(metadata[field]):
                errors.append(f"{field} должен быть false")
    return errors


def validate_package(package_dir: Path, allow_public_safe: bool = False) -> list[str]:
    if not package_dir.is_dir():
        return [f"{package_dir}: папка не найдена"]
    markdown_files = sorted(package_dir.rglob("*.md"))
    if not markdown_files:
        return [f"{package_dir}: Markdown-файлы не найдены"]

    errors: list[str] = []
    for path in markdown_files:
        for error in validate_file(path, allow_public_safe=allow_public_safe):
            errors.append(f"{path.relative_to(package_dir)}: {error}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Проверяет метаданные и переносимость пакета общей базы знаний."
    )
    parser.add_argument("package_dir", type=Path, help="Папка экспортированного пакета")
    parser.add_argument(
        "--allow-public-safe", action="store_true",
        help="Разрешить public_safe: true после отдельного решения владельца",
    )
    args = parser.parse_args()
    errors = validate_package(args.package_dir, args.allow_public_safe)
    if errors:
        print("Проверка не пройдена:")
        for error in errors:
            print(f"- {error}")
        return 1
    count = len(list(args.package_dir.rglob("*.md")))
    print(f"Проверка пройдена: {count} Markdown-файлов.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

