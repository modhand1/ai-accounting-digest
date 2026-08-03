import importlib.util
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock


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
        remote = root / "remote.git"
        self.git_run(root, "init", "--bare", "--initial-branch=main", str(remote))
        repo.mkdir()
        self.git_run(repo, "init", "--initial-branch=main")
        self.git_run(repo, "config", "user.name", "Backup Test")
        self.git_run(repo, "config", "user.email", "backup-test@example.invalid")
        (repo / "README.md").write_text("Проверка восстановления\n", encoding="utf-8")
        self.git_run(repo, "add", "README.md")
        self.git_run(repo, "commit", "-m", "Initial test")
        self.git_run(repo, "remote", "add", "origin", str(remote))
        self.git_run(repo, "push", "--set-upstream", "origin", "main")
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
                now=moment,
            )
            self.assertEqual("unchanged", duplicate["status"])

    def test_destination_inside_repository_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repository(Path(tmp))
            with self.assertRaises(ValueError):
                BACKUP.assert_safe_locations(repo.resolve(), (repo / "backups").resolve())

    def test_remote_url_credentials_query_and_fragment_are_removed(self):
        value = BACKUP.safe_remote_url(
            "https://user:password@example.invalid/project.git"
            "?access_token=query-secret#fragment-secret"
        )
        self.assertEqual("https://example.invalid/project.git", value)

    def test_scp_style_remote_user_is_removed(self):
        value = BACKUP.safe_remote_url("secret-user@example.invalid:project.git")
        self.assertEqual("example.invalid:project.git", value)

    def test_portable_git_uses_https_helper_without_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executable = root / "portable-git" / "cmd" / "git.exe"
            helper = root / "portable-git" / "mingw64" / "bin" / "git-remote-https.exe"
            executable.parent.mkdir(parents=True)
            helper.parent.mkdir(parents=True)
            executable.touch()
            helper.touch()

            command = BACKUP.git_command(
                str(executable), "fetch", "origin", "main"
            )

            self.assertIn(f"--exec-path={helper.parent}", command)
            self.assertIn("credential.helper=", command)
            self.assertFalse(any("safe.directory=" in item for item in command))
            self.assertEqual(["fetch", "origin", "main"], command[-3:])

    def test_untrusted_transport_remote_is_rejected_before_git_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "source"
            repo.mkdir()
            self.git_run(repo, "init", "--initial-branch=main")
            self.git_run(
                repo,
                "remote",
                "add",
                "origin",
                "ssh://example.invalid/repository.git",
            )

            with self.assertRaisesRegex(ValueError, "HTTPS"):
                BACKUP.read_public_remote_url(repo, "origin")

    def test_git_environment_ignores_system_and_user_config(self):
        with mock.patch.dict(
            BACKUP.os.environ,
            {
                "GIT_CONFIG_COUNT": "1",
                "GIT_PROXY_COMMAND": "untrusted-command",
            },
        ):
            environment = BACKUP.git_environment()
        self.assertEqual("1", environment["GIT_CONFIG_NOSYSTEM"])
        self.assertEqual(BACKUP.os.devnull, environment["GIT_CONFIG_GLOBAL"])
        self.assertEqual("0", environment["GIT_TERMINAL_PROMPT"])
        self.assertNotIn("GIT_CONFIG_COUNT", environment)
        self.assertNotIn("GIT_PROXY_COMMAND", environment)

    def test_cli_rejects_source_ref_and_no_fetch_overrides(self):
        parser = BACKUP.build_parser()
        for forbidden_argument in ("--source-ref", "--no-fetch"):
            with self.subTest(forbidden_argument=forbidden_argument):
                with self.assertRaises(SystemExit):
                    parser.parse_args(
                        ["--destination", "backup", forbidden_argument]
                    )


if __name__ == "__main__":
    unittest.main()
