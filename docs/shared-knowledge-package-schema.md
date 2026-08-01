# Контракт пакета общей базы знаний

Этот документ задаёт единый формат для экспортных копий материалов сайта в общую базу. Пакет в Google Drive — удобная копия для поиска и работы агентов, но не новый источник истины.

## Где находится канон

- Код, шаблоны, изображения и документы, уже опубликованные в GitHub, остаются каноническими в GitHub.
- Локальные исследования и редакционные документы, которых нет в публичном репозитории, остаются каноническими в личном проекте. В экспортной копии сохраняется только относительный путь без имени пользователя и адреса компьютера.
- Спецификация агента «Исследователь новостей ИИ» канонически ведётся в общей базе отдельным объектом. Копия плана внутри пакета сайта является только справочной и не даёт права запускать автоматизацию, изменять сайт или публиковать материалы.

## Обязательный frontmatter каждого Markdown-файла

```yaml
---
package_id: "SITE-AI-ACCOUNTING-YYYY-MM-DD"
corpus: "website_knowledge"
document_role: "article"
status: "draft"
public_safe: false
source: "personal_project_ai_accounting_digest"
canonical_source_type: "github"
canonical_repository: "https://github.com/modhand1/ai-accounting-digest"
canonical_path: "content.py#material-01"
date_exported: "YYYY-MM-DD"
freshness_sensitive: false
---
```

Допустимые `document_role`: `passport`, `article`, `project_rule`, `research`, `audit`, `safety`, `agent_reference`.

Допустимые `canonical_source_type`: `github`, `local_project`, `shared_base`. Поле `canonical_path` всегда содержит относительный путь или устойчивый идентификатор, но не абсолютный путь вида `C:\Users\...`.

Для фактов, которые могут устаревать, обязательны:

```yaml
freshness_sensitive: true
last_verified_at: "YYYY-MM-DD"
```

`public_safe: true` нельзя выставлять автоматически. Это отдельное решение владельца после проверки конкретного документа.

## Дополнительные поля справочной копии плана агента

```yaml
document_role: "agent_reference"
canonical_source_type: "shared_base"
canonical_path: "Агент — исследователь новостей ИИ"
canonical_status: "draft_unnumbered"
automation_authority: false
site_write_access: false
publication_allowed: false
```

В начале самого документа также должна быть заметная пометка: это неканоническая справочная копия; решения принимаются в отдельной карточке агента в общей базе.

## Порядок обновления

1. Изменить канонический источник.
2. Создать новую версию экспортного пакета, не удаляя предыдущую.
3. Добавить или обновить frontmatter во всех Markdown-файлах.
4. Запустить `python tools/validate_shared_knowledge_package.py <папка-пакета>`.
5. Загрузить проверенную версию в общую базу и отметить предыдущую как `superseded`.
6. Только после ручной проверки менять статус или `public_safe`.

