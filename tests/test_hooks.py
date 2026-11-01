import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent


class HookTest(unittest.TestCase):
    """Runs real git in a temporary repo with a temporary home, so your real pet is safe."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name) / "home"
        self.repo = Path(tmp.name) / "repo"
        self.home.mkdir()
        self.repo.mkdir()
        self.env = {
            **os.environ,
            "HOME": str(self.home),
            "PYTHONPATH": str(PROJECT),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        }
        self.git("init", "-q", "-b", "main")
        self.hook = self.repo / ".git" / "hooks" / "post-commit"
        self.save = self.home / ".terminal-tamagotchi" / "pet.json"

    def run_in_repo(self, *command, cwd=None):
        return subprocess.run(command, cwd=cwd or self.repo, env=self.env, capture_output=True, text=True)

    def git(self, *args):
        result = self.run_in_repo("git", *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def pet(self, *args, cwd=None):
        return self.run_in_repo(sys.executable, "-m", "tamagotchi.cli", *args, cwd=cwd)

    def commit(self, lines=1):
        (self.repo / "file.txt").write_text("".join(f"{i} {os.urandom(4).hex()}\n" for i in range(lines)))
        self.git("add", "file.txt")
        return self.git("commit", "-q", "-m", "a commit")

    def pet_state(self):
        return json.loads(self.save.read_text())

    def existing_hook(self, text):
        self.hook.parent.mkdir(exist_ok=True)
        self.hook.write_text(text)
        self.hook.chmod(0o755)

    def test_first_commit_hatches_the_pet(self):
        self.assertEqual(self.pet("install").returncode, 0)
        result = self.commit()
        # Git sends a post-commit hook's output to stderr.
        self.assertIn("hatched", result.stderr)
        self.assertEqual(self.pet_state()["level"], 1)

    def test_commit_size_sets_the_reward(self):
        self.pet("install")
        self.commit(lines=100)
        self.assertEqual(self.pet_state()["xp"], 15)
        self.commit(lines=5000)
        # 5000 lines added plus 100 removed, capped at the maximum reward.
        self.assertEqual(self.pet_state()["xp"], 35)

    def test_install_works_from_a_subfolder(self):
        sub = self.repo / "a" / "b"
        sub.mkdir(parents=True)
        self.assertEqual(self.pet("install", cwd=sub).returncode, 0)
        self.assertTrue(self.hook.exists())

    def test_install_twice_keeps_one_copy(self):
        self.pet("install")
        result = self.pet("install")
        self.assertIn("Already installed", result.stdout)
        self.assertEqual(self.hook.read_text().count("feed --commit"), 1)

    def test_install_outside_a_repo_fails_politely(self):
        result = self.pet("install", cwd=self.home)
        self.assertEqual(result.returncode, 1)
        self.assertIn("isn't a git repository", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_existing_hook_still_runs_and_pet_gets_fed(self):
        # Ending in `exit 0` is why the pet goes first: anything appended would never run.
        marker = self.home / "ran"
        self.existing_hook(f"#!/bin/sh\ntouch {marker}\nexit 0\n")
        result = self.pet("install")
        self.assertIn("kept it", result.stdout)
        self.commit()
        self.assertTrue(marker.exists())
        self.assertEqual(self.pet_state()["level"], 1)

    def test_uninstall_restores_an_existing_hook_exactly(self):
        original = "#!/bin/bash\necho hi\nexit 0\n"
        self.existing_hook(original)
        self.pet("install")
        self.assertNotEqual(self.hook.read_text(), original)
        self.pet("uninstall")
        self.assertEqual(self.hook.read_text(), original)
        self.assertTrue(os.access(self.hook, os.X_OK))

    def test_uninstall_deletes_a_hook_we_created(self):
        self.pet("install")
        self.pet("uninstall")
        self.assertFalse(self.hook.exists())
        self.commit()
        self.assertFalse(self.save.exists())

    def test_uninstall_when_not_installed_changes_nothing(self):
        original = "#!/bin/sh\necho mine\n"
        self.existing_hook(original)
        result = self.pet("uninstall")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.hook.read_text(), original)

    def test_hooks_we_cant_safely_edit_are_refused(self):
        python_hook = "#!/usr/bin/env python3\nprint('hi')\n"
        self.existing_hook(python_hook)
        self.assertEqual(self.pet("install").returncode, 1)
        self.assertEqual(self.hook.read_text(), python_hook)

        disabled_hook = "#!/bin/sh\necho old\n"
        self.existing_hook(disabled_hook)
        self.hook.chmod(0o644)
        self.assertEqual(self.pet("install").returncode, 1)
        self.assertEqual(self.hook.read_text(), disabled_hook)

        self.hook.unlink()
        self.hook.symlink_to(self.home / "shared-hook")
        self.assertEqual(self.pet("install").returncode, 1)
        self.assertTrue(self.hook.is_symlink())

    def test_bad_save_file_cant_stop_a_commit(self):
        self.pet("install")
        self.save.parent.mkdir()
        self.save.write_text(json.dumps({"hunger": "lots", "level": 1}))
        result = self.commit()
        self.assertIn("your commit is fine", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_missing_python_cant_stop_a_commit(self):
        self.pet("install")
        self.hook.write_text(self.hook.read_text().replace(sys.executable, "/no/such/python"))
        self.commit()
        self.assertEqual(self.git("rev-list", "--count", "HEAD").stdout.strip(), "1")


if __name__ == "__main__":
    unittest.main()
