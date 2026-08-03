import importlib.util
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parent / "tools" / "check_public_repo.py"
SPEC = importlib.util.spec_from_file_location("public_repo_check", MODULE_PATH)
CHECKER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(CHECKER)


class PublicRepositoryCheckTests(unittest.TestCase):
    def validate(self, relative_path: str, content: str = "Безопасный текст"):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return CHECKER.validate_file(root, path)

    def test_safe_text_file_passes(self):
        self.assertEqual([], self.validate("docs/article.md"))

    def test_private_directory_is_rejected(self):
        errors = self.validate("private/research.md")
        self.assertTrue(any("запрещённая папка" in error for error in errors))

    def test_archive_is_rejected(self):
        errors = self.validate("release/site.zip")
        self.assertTrue(any("запрещённый тип" in error for error in errors))

    def test_real_user_path_is_rejected(self):
        errors = self.validate(
            "docs/audit.md",
            r"C:\Users\Person\secret.txt",  # public-scan: allow
        )
        self.assertTrue(any("пользовательский путь" in error for error in errors))

    def test_token_is_rejected(self):
        token = "ghp_" + "A" * 36
        errors = self.validate("config.txt", token)
        self.assertTrue(any("токен GitHub" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
