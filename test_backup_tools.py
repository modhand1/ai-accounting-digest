import importlib.util
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).parent


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


BACKUP = load_module("backup_project", ROOT / "tools" / "backup_project.py")
RESTORE = load_module("restore_backup", ROOT / "tools" / "restore_backup.py")


class BackupToolsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.git = shutil.which("git")
        if not cls.git:
            raise unittest.SkipTest("Git не найден")

    def git_run(self, repo: Path, *arguments: str) -> str:
        result = subprocess.run(
            [self.git, *arguments],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return result.stdout.strip()

    def make_repository(self, root: Path) -> Path:
        repo = root / "source"
        repo.mkdir()
        self.git_run(repo, "init", "--initial-branch=main")
        self.git_run(repo, "config", "user.name", "Backup Test")
        self.git_run(repo, "config", "user.email", "backup-test@example.invalid")
        (repo / "README.md").write_text("Проверка восстановления\n", encoding="utf-8")
        self.git_run(repo, "add", "README.md")
        self.git_run(repo, "commit", "-m", "Initial test")
        self.git_run(repo, "remote", "add", "origin", "https://example.invalid/project.git")
        return repo

    def test_backup_is_created_verified_and_not_duplicated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = self.make_repository(root)
            destination = root / "drive-backups"
            moment = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)

            result = BACKUP.create_backup(
                repo=repo,
                destination=destination,
                git_executable=self.git,
                source_ref="refs/heads/main",
                fetch=False,
                now=moment,
            )

            self.assertEqual("created", result["status"])
            archive = Path(result["archive_directory"])
            self.assertTrue((archive / "SHA256SUMS.txt").is_file())
            verified = RESTORE.verify_archive(archive, git_executable=self.git)
            self.assertEqual(result["commit_sha"], verified["commit_sha"])

            duplicate = BACKUP.create_backup(
                repo=repo,
                destination=destination,
                git_executable=self.git,
                source_ref="refs/heads/main",
                fetch=False,
                now=moment,
            )
            self.assertEqual("unchanged", duplicate["status"])

    def test_destination_inside_repository_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repository(Path(tmp))
            with self.assertRaises(ValueError):
                BACKUP.assert_safe_locations(repo.resolve(), (repo / "backups").resolve())


if __name__ == "__main__":
    unittest.main()
