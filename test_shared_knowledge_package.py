import importlib.util
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parent / "tools" / "validate_shared_knowledge_package.py"
SPEC = importlib.util.spec_from_file_location("package_validator", MODULE_PATH)
VALIDATOR = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(VALIDATOR)


def document(**overrides: str) -> str:
    values = {
        "package_id": '"SITE-AI-ACCOUNTING-2026-07-31"',
        "corpus": '"website_knowledge"',
        "document_role": '"article"',
        "status": '"draft"',
        "public_safe": "false",
        "source": '"personal_project_ai_accounting_digest"',
        "canonical_source_type": '"github"',
        "canonical_repository": '"https://github.com/modhand1/ai-accounting-digest"',
        "canonical_path": '"content.py#material-01"',
        "date_exported": '"2026-07-31"',
        "freshness_sensitive": "false",
    }
    values.update(overrides)
    lines = ["---", *(f"{key}: {value}" for key, value in values.items()), "---", "# Тест"]
    return "\n".join(lines)


class SharedKnowledgePackageValidatorTests(unittest.TestCase):
    def test_valid_document_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "article.md"
            path.write_text(document(), encoding="utf-8")
            self.assertEqual([], VALIDATOR.validate_file(path))

    def test_absolute_user_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audit.md"
            path.write_text(document() + "\nC:\\Users\\Name\\secret.png", encoding="utf-8")
            self.assertIn(
                "найден абсолютный пользовательский путь",
                VALIDATOR.validate_file(path),
            )

    def test_fresh_claim_requires_verification_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "research.md"
            path.write_text(document(freshness_sensitive="true"), encoding="utf-8")
            errors = VALIDATOR.validate_file(path)
            self.assertTrue(any("last_verified_at" in error for error in errors))

    def test_agent_reference_cannot_authorize_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "agent.md"
            path.write_text(
                document(
                    document_role='"agent_reference"',
                    canonical_source_type='"shared_base"',
                    canonical_path='"Агент — исследователь новостей ИИ"',
                    canonical_status='"draft_unnumbered"',
                    automation_authority="true",
                    site_write_access="false",
                    publication_allowed="false",
                ),
                encoding="utf-8",
            )
            self.assertIn(
                "automation_authority должен быть false",
                VALIDATOR.validate_file(path),
            )


if __name__ == "__main__":
    unittest.main()

