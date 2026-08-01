"""Экспорт материалов сайта в переносимый Markdown-пакет общей базы знаний.

Запуск из корня проекта:
    python tools/export_shared_knowledge_package.py <новая-папка-назначение>

Экспортёр намеренно не перезаписывает непустую папку: каждая выгрузка является
отдельной версией. Все Markdown-файлы получают единый обязательный frontmatter.
"""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from content import MATERIALS  # noqa: E402


CANONICAL_REPOSITORY = "https://github.com/modhand1/ai-accounting-digest"
EXPORT_DATE = date.today().isoformat()
PACKAGE_ID = f"SITE-AI-ACCOUNTING-{EXPORT_DATE}"

# Файлы, наличие которых было подтверждено в публичной ветке main. Остальные
# локальные исследования и черновики не публикуются и ссылаются только на
# относительный путь внутри личного проекта.
PACKAGE_SECTIONS = {
    "02_ПРАВИЛА_И_ГОЛОС": [
        {
            "path": "PROJECT_RULES.md",
            "role": "project_rule",
            "source_type": "local_project",
            "fresh": False,
        },
        {
            "path": "voice.md",
            "role": "project_rule",
            "source_type": "local_project",
            "fresh": False,
        },
        {
            "path": "PROMPTS.md",
            "role": "project_rule",
            "source_type": "github",
            "fresh": False,
        },
    ],
    "03_ИССЛЕДОВАНИЯ_И_МЕТОДИКА": [
        {
            "path": "docs/editorial-research-ai-finance-authors.md",
            "role": "research",
            "source_type": "local_project",
            "fresh": True,
        },
        {
            "path": "docs/editorial-standard.md",
            "role": "project_rule",
            "source_type": "local_project",
            "fresh": False,
        },
        {
            "path": "docs/lesson-function-generator-and-ai.md",
            "role": "research",
            "source_type": "local_project",
            "fresh": True,
        },
        {
            "path": "docs/weekly-intelligence-agent-plan.md",
            "role": "agent_reference",
            "source_type": "shared_base",
            "canonical_path": "Агент — исследователь новостей ИИ",
            "fresh": True,
            "extra": {
                "canonical_status": "draft_unnumbered",
                "automation_authority": False,
                "site_write_access": False,
                "publication_allowed": False,
            },
            "notice": (
                "> **Важно: это неканоническая справочная копия.** "
                "Решения по агенту принимаются в отдельной карточке "
                "«Агент — исследователь новостей ИИ» в общей базе. Эта копия "
                "не разрешает запуск автоматизации, изменение сайта или публикацию."
            ),
        },
    ],
    "04_РЕДАКЦИОННЫЕ_ПРОВЕРКИ": [
        {
            "path": "docs/article-01-editorial-audit.md",
            "role": "audit",
            "source_type": "local_project",
            "fresh": False,
        },
        {
            "path": "docs/article-03-editorial-audit.md",
            "role": "audit",
            "source_type": "local_project",
            "fresh": True,
        },
        {
            "path": "docs/article-04-05-editorial-audit.md",
            "role": "audit",
            "source_type": "local_project",
            "fresh": True,
        },
        {
            "path": "docs/article-10-guardrails-editorial-audit.md",
            "role": "audit",
            "source_type": "local_project",
            "fresh": True,
        },
        {
            "path": "docs/articles-02-06-09-editorial-audit.md",
            "role": "audit",
            "source_type": "local_project",
            "fresh": True,
        },
        {
            "path": "docs/design-qa.md",
            "role": "audit",
            "source_type": "github",
            "fresh": False,
        },
        {
            "path": "docs/prelaunch-checkpoint-2026-07-31.md",
            "role": "audit",
            "source_type": "local_project",
            "fresh": False,
        },
    ],
    "05_БЕЗОПАСНОСТЬ_И_ЗАПУСК": [
        {
            "path": "docs/compliance-and-launch-plan.md",
            "role": "safety",
            "source_type": "local_project",
            "fresh": True,
        },
        {
            "path": "docs/data-processing-register.md",
            "role": "safety",
            "source_type": "local_project",
            "fresh": True,
        },
        {
            "path": "docs/launch-compliance-checklist.md",
            "role": "safety",
            "source_type": "local_project",
            "fresh": True,
        },
        {
            "path": "docs/product-spec-ai-workflow.md",
            "role": "safety",
            "source_type": "local_project",
            "fresh": True,
        },
        {
            "path": "docs/secure-document-ai-workflow.md",
            "role": "safety",
            "source_type": "local_project",
            "fresh": True,
        },
        {
            "path": "PUBLICATION.md",
            "role": "safety",
            "source_type": "github",
            "fresh": True,
        },
        {
            "path": "README.md",
            "role": "project_rule",
            "source_type": "github",
            "fresh": False,
        },
        {
            "path": "ОТКРЫТЬ_СНАЧАЛА.md",
            "role": "project_rule",
            "source_type": "local_project",
            "fresh": False,
        },
    ],
}


ARTICLE_CANONICAL_PATHS = {
    "01": "content.py#material-01",
    "02": "materials_course.py#material-02",
    "03": "content.py#material-03",
    "04": "materials_advanced.py#material-04",
    "05": "materials_advanced.py#material-05",
    "06": "materials_course.py#material-06",
    "07": "materials_course.py#material-07",
    "08": "materials_course.py#material-08",
    "09": "materials_course.py#material-09",
    "10": "materials_course.py#material-10",
}

# Материалы 02–10 содержат ссылки на действующие стандарты, законы, сервисы,
# тарифы или документацию продуктов и требуют проверки актуальности.
FRESHNESS_SENSITIVE_ARTICLES = {f"{number:02d}" for number in range(2, 11)}

WINDOWS_USER_PREFIX = re.compile(
    r"[A-Za-z]:[\\/](?:Users|Documents and Settings)[\\/][^\\/\r\n`]+[\\/]",
    re.IGNORECASE,
)
UNIX_USER_PREFIX = re.compile(r"/(?:Users|home)/[^/\r\n`]+/", re.IGNORECASE)


def yaml_text(value: object) -> str:
    """Минимальное безопасное представление строки для YAML frontmatter."""
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def yaml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return yaml_text(value)


def make_frontmatter(
    *,
    role: str,
    source_type: str,
    canonical_path: str,
    freshness_sensitive: bool,
    extra: dict[str, object] | None = None,
    title: str | None = None,
) -> str:
    fields: list[tuple[str, object]] = [
        ("package_id", PACKAGE_ID),
        ("corpus", "website_knowledge"),
        ("document_role", role),
        ("status", "draft"),
        ("public_safe", False),
        ("source", "personal_project_ai_accounting_digest"),
        ("canonical_source_type", source_type),
    ]
    if source_type == "github":
        fields.append(("canonical_repository", CANONICAL_REPOSITORY))
    fields.extend(
        [
            ("canonical_path", canonical_path),
            ("date_exported", EXPORT_DATE),
            ("freshness_sensitive", freshness_sensitive),
        ]
    )
    if freshness_sensitive:
        fields.append(("last_verified_at", EXPORT_DATE))
    if extra:
        fields.extend(extra.items())
    if title:
        fields.append(("title", title))
    lines = ["---", *(f"{key}: {yaml_value(value)}" for key, value in fields), "---"]
    return "\n".join(lines)


def strip_existing_frontmatter(text: str) -> str:
    """Удаляет прежний frontmatter, чтобы в экспорте оставался один блок."""
    lines = text.lstrip("\ufeff").splitlines()
    if not lines or lines[0].strip() != "---":
        return text.lstrip("\ufeff")
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "\n".join(lines[index + 1 :]).lstrip("\n")
    return text.lstrip("\ufeff")


def remove_absolute_user_paths(text: str) -> str:
    """Делает встречающиеся в справочных текстах пути переносимыми."""
    text = WINDOWS_USER_PREFIX.sub("", text)
    return UNIX_USER_PREFIX.sub("", text)


def render_article(material: dict) -> str:
    number = material["number"]
    frontmatter = make_frontmatter(
        role="article",
        source_type="github",
        canonical_path=ARTICLE_CANONICAL_PATHS[number],
        freshness_sensitive=number in FRESHNESS_SENSITIVE_ARTICLES,
        title=material["headline"],
    )
    lines = [
        frontmatter,
        "",
        f"# {material['headline']}",
        "",
        f"**Формат:** {material['kind']} · {material['read_time']}",
        "",
        material["lead"],
        "",
        "**Автор:** Морозова Юлия — практикующий заместитель главного бухгалтера, 20 лет в профессии.",
        "",
    ]

    for index, section in enumerate(material["sections"], start=1):
        lines.extend([f"## {index:02d}. {section['heading']}", ""])

        for paragraph in section.get("paragraphs", []):
            lines.extend([paragraph, ""])

        for bullet in section.get("bullets", []):
            lines.append(f"- {bullet}")
        if section.get("bullets"):
            lines.append("")

        table = section.get("table")
        if table:
            headers = [str(item) for item in table["headers"]]
            lines.extend(
                [
                    "| " + " | ".join(headers) + " |",
                    "| " + " | ".join("---" for _ in headers) + " |",
                ]
            )
            for row in table["rows"]:
                cells = [str(cell).replace("|", "\\|").replace("\n", "<br>") for cell in row]
                lines.append("| " + " | ".join(cells) + " |")
            lines.append("")

        callout = section.get("callout")
        if callout:
            lines.extend([f"> **{callout['label']}**", f"> ### {callout['title']}"])
            if callout.get("text"):
                lines.append(f"> {callout['text']}")
            for item in callout.get("items", []):
                lines.append(f"> - {item}")
            lines.append("")

        prompt = section.get("prompt")
        if prompt:
            lines.extend(
                [
                    f"### {prompt.get('eyebrow', 'Можно скопировать')}: {prompt['title']}",
                    "",
                    "```text",
                    prompt["text"],
                    "```",
                    "",
                ]
            )

        links = section.get("links")
        if links:
            lines.extend(["### Источники и полезные страницы", ""])
            for link in links:
                lines.append(f"- [{link['title']}]({link['url']})")
            lines.append("")

    lines.extend(["## Сделайте сейчас", "", material["action"], ""])
    return "\n".join(lines)


def render_support_document(spec: dict[str, object]) -> str:
    relative_path = str(spec["path"])
    source_text = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
    body = remove_absolute_user_paths(strip_existing_frontmatter(source_text))
    canonical_path = str(spec.get("canonical_path", relative_path))
    frontmatter = make_frontmatter(
        role=str(spec["role"]),
        source_type=str(spec["source_type"]),
        canonical_path=canonical_path,
        freshness_sensitive=bool(spec["fresh"]),
        extra=spec.get("extra"),
    )
    parts = [frontmatter, ""]
    if spec.get("notice"):
        parts.extend([str(spec["notice"]), ""])
    parts.append(body.rstrip())
    parts.append("")
    return "\n".join(parts)


def write_manifest(destination: Path) -> None:
    article_list = "\n".join(
        f"- {item['number']}. {item['headline']} (`{item['slug']}`)" for item in MATERIALS
    )
    frontmatter = make_frontmatter(
        role="passport",
        source_type="local_project",
        canonical_path="tools/export_shared_knowledge_package.py#package-manifest",
        freshness_sensitive=False,
        title="Сайт ИИ × БУХГАЛТЕР — пакет материалов",
    )
    manifest = f"""{frontmatter}

# Сайт ИИ × БУХГАЛТЕР — пакет материалов

Это копия знаний и текстов личного проекта Морозовой Юлии для общей базы Codex.
Пакет не является рабочим кейсом работодателя, ему не присваивается номер CASE,
а основной каталог кейсов этим экспортом не изменяется.

## Что является первоисточником

- Технический первоисточник сайта: репозиторий `modhand1/ai-accounting-digest`.
- Локальные исследования и черновики канонически хранятся только в личном проекте; в метаданных указаны относительные пути.
- Эта папка — читаемая копия для поиска, анализа и совместной работы из домашнего и рабочего Codex.
- Статус материалов на дату экспорта: предзапускной черновик.
- `public_safe: false` означает, что решение о публикации принимается Юлией отдельно после проверки.
- Рабочие документы, реальные реквизиты и сведения работодателя в пакет не включены; примеры в статьях учебные и вымышленные.

## Состав

1. `01_МАТЕРИАЛЫ_САЙТА` — десять полнотекстовых статей в Markdown.
2. `02_ПРАВИЛА_И_ГОЛОС` — правила проекта, стиль текстов и сохранённые промпты.
3. `03_ИССЛЕДОВАНИЯ_И_МЕТОДИКА` — исследования авторов, редакционный стандарт и методические заметки.
4. `04_РЕДАКЦИОННЫЕ_ПРОВЕРКИ` — результаты проверок статей и предзапускной контроль.
5. `05_БЕЗОПАСНОСТЬ_И_ЗАПУСК` — документы по данным, безопасности, архитектуре функции и публикации.

## Материалы сайта

{article_list}

## Правило обновления

Новые изменения сначала вносятся в канонический источник и проверяются. После
утверждения создаётся новая версия пакета. Предыдущая версия не удаляется и не
перезаписывается.
"""
    (destination / "00_ПАСПОРТ_ПАКЕТА.md").write_text(manifest, encoding="utf-8")


def export(destination: Path) -> None:
    if destination.exists() and any(destination.iterdir()):
        raise SystemExit(f"Папка уже существует и не пуста: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    articles_dir = destination / "01_МАТЕРИАЛЫ_САЙТА"
    articles_dir.mkdir(exist_ok=True)

    write_manifest(destination)
    for material in MATERIALS:
        filename = f"{material['number']}_{material['slug']}.md"
        (articles_dir / filename).write_text(render_article(material), encoding="utf-8")

    for section_name, documents in PACKAGE_SECTIONS.items():
        section_dir = destination / section_name
        section_dir.mkdir(exist_ok=True)
        for spec in documents:
            source_name = Path(str(spec["path"])).name
            (section_dir / source_name).write_text(
                render_support_document(spec), encoding="utf-8"
            )


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Укажите единственную новую папку назначения.")
    export(Path(sys.argv[1]).resolve())
    print(f"Готово: {Path(sys.argv[1]).resolve()}")


if __name__ == "__main__":
    main()
