import contextlib
import http.server
import io
import json
import os
import subprocess
import tempfile
import threading
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from tamagotchi import agent, art, claude, cli, hooks, pet as pet_logic, social, storage

NOON = datetime(2026, 1, 15, 12).timestamp()
DAY = pet_logic.SECONDS_PER_DAY


def good_snapshot(**changes):
    pet = {**pet_logic.new_pet(NOON), "xp": 320, "level": 4, "streak": 6, "last_fed": "2026-01-15"}
    return {**social.snapshot(pet), **changes}


class TempFilesTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)
        for target, attribute, value in (
            (social, "FRIENDS_PATH", self.folder / "friends.json"),
            (storage, "PATH", self.folder / "pet.json"),
            (claude, "PROJECTS", self.folder / "no-logs"),
            (claude, "LIMIT_PATH", self.folder / "limit.json"),
            (agent, "AGENT_PATH", self.folder / "agent.json"),
        ):
            patcher = mock.patch.object(target, attribute, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()


class SnapshotTest(unittest.TestCase):
    def test_only_public_fields_are_published(self):
        pet = {**pet_logic.new_pet(NOON), "leveled_at": NOON, "secret": "x"}
        self.assertEqual(
            set(social.snapshot(pet)), {"name", "xp", "hunger", "mood", "streak", "last_fed", "last_update"}
        )

    def test_good_snapshot_loads(self):
        pet = social.from_snapshot(good_snapshot())
        self.assertEqual((pet["name"], pet["xp"], pet["streak"]), ("Porky", 320, 6))

    def test_level_comes_from_xp_not_the_file(self):
        self.assertEqual(social.from_snapshot({**good_snapshot(), "level": 999})["level"], 4)

    def test_stats_are_clamped(self):
        pet = social.from_snapshot(good_snapshot(hunger=50, mood=-3))
        self.assertEqual((pet["hunger"], pet["mood"]), (5, 0))

    def test_hostile_snapshots_are_refused(self):
        bad = [
            good_snapshot(name="\033[2Jevil"),
            good_snapshot(name="a\nb"),
            good_snapshot(name="x" * 21),
            good_snapshot(name=""),
            good_snapshot(name=5),
            good_snapshot(xp=10 ** 30),
            good_snapshot(xp=-1),
            good_snapshot(xp=1.5),
            good_snapshot(xp=True),
            good_snapshot(xp="lots"),
            good_snapshot(hunger=float("nan")),
            good_snapshot(mood=float("inf")),
            good_snapshot(streak=-1),
            good_snapshot(last_update="soon"),
            good_snapshot(last_fed="yesterday"),
            good_snapshot(last_fed=5),
            {},
            [],
            "text",
            None,
        ]
        for data in bad:
            with self.assertRaises((ValueError, KeyError, TypeError), msg=repr(data)):
                social.from_snapshot(data)


class ReadmeTest(TempFilesTest):
    def setUp(self):
        super().setUp()
        self.pet = {**pet_logic.new_pet(NOON), "level": 1}
        self.readme = self.folder / "README.md"

    def test_creates_a_missing_readme(self):
        social.update_readme(self.folder, self.pet, NOON)
        self.assertIn("Porky", self.readme.read_text())

    def test_keeps_the_rest_of_the_readme_when_updating_twice(self):
        self.readme.write_text("# Hi, I'm Ryan\n\nI like $1 and \\1 things.\n")
        social.update_readme(self.folder, self.pet, NOON)
        social.update_readme(self.folder, {**self.pet, "name": "Mochi"}, NOON)
        text = self.readme.read_text()
        self.assertTrue(text.startswith("# Hi, I'm Ryan\n\nI like $1 and \\1 things.\n"))
        self.assertEqual(text.count(social.START), 1)
        self.assertIn("Mochi", text)
        self.assertNotIn("Porky", text)

    def test_text_after_the_markers_survives(self):
        self.readme.write_text(f"before\n{social.START}\nold\n{social.END}\nafter\n")
        social.update_readme(self.folder, self.pet, NOON)
        text = self.readme.read_text()
        self.assertTrue(text.startswith("before\n"))
        self.assertTrue(text.endswith("\nafter\n"))
        self.assertNotIn("old", text)

    def test_no_terminal_colors_end_up_in_the_readme(self):
        with mock.patch.object(art, "COLOR", True):
            social.update_readme(self.folder, self.pet, NOON)
        self.assertNotIn("\033", self.readme.read_text())

    def test_profile_update_applies_hunger_since_the_share(self):
        (self.folder / "pet.json").write_text(json.dumps(good_snapshot()))
        social.profile_update(self.folder, NOON + 3 * DAY)
        self.assertIn("♥♡♡♡♡", self.readme.read_text())

    def test_profile_update_doesnt_change_the_snapshot(self):
        (self.folder / "pet.json").write_text(json.dumps(good_snapshot()))
        before = (self.folder / "pet.json").read_text()
        social.profile_update(self.folder, NOON + DAY)
        self.assertEqual((self.folder / "pet.json").read_text(), before)

    def test_profile_update_without_a_snapshot_fails_politely(self):
        with self.assertRaises(hooks.HookError):
            social.profile_update(self.folder, NOON)


class ShareTest(TempFilesTest):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ, {
            "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@example.com",
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
        })
        patcher.start()
        self.addCleanup(patcher.stop)
        self.repo = self.folder / "me"
        self.repo.mkdir()
        self.bare = self.folder / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.bare)], check=True)
        self.git("init", "-q", "-b", "main")
        self.git("remote", "add", "origin", "https://github.com/me/me.git")
        # The name check reads the fetch URL. Pushes go to a local folder.
        self.git("remote", "set-url", "--push", "origin", str(self.bare))
        self.git("commit", "-q", "--allow-empty", "-m", "start")
        self.git("push", "-q", "-u", "origin", "main")
        cwd = os.getcwd()
        os.chdir(self.repo)
        self.addCleanup(os.chdir, cwd)
        self.pet = {**pet_logic.new_pet(NOON), "level": 1, "xp": 10}

    def git(self, *args):
        result = subprocess.run(["git", "-C", str(self.repo), *args], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_share_writes_the_files_without_committing(self):
        message = social.share(self.pet, NOON)
        self.assertIn("git push", message)
        self.assertEqual(json.loads((self.repo / "pet.json").read_text())["xp"], 10)
        self.assertEqual((self.repo / social.WORKFLOW_PATH).read_text(), social.WORKFLOW)
        self.assertIn("Porky", (self.repo / "README.md").read_text())
        self.assertEqual(self.git("rev-list", "--count", "HEAD").strip(), "1")

    def test_share_from_a_subfolder_writes_to_the_top(self):
        sub = self.repo / "sub"
        sub.mkdir()
        os.chdir(sub)
        social.share(self.pet, NOON)
        self.assertTrue((self.repo / "pet.json").exists())
        self.assertFalse((sub / "pet.json").exists())

    def test_share_push_publishes_only_its_own_files(self):
        (self.repo / "private.txt").write_text("not this")
        social.share(self.pet, NOON, push=True)
        pushed = subprocess.run(
            ["git", "--git-dir", str(self.bare), "ls-tree", "-r", "--name-only", "main"],
            capture_output=True, text=True,
        ).stdout.split()
        self.assertEqual(sorted(pushed), sorted(["pet.json", "README.md", social.WORKFLOW_PATH]))

    def test_sharing_nothing_new_makes_no_commit(self):
        social.share(self.pet, NOON, push=True)
        count = self.git("rev-list", "--count", "HEAD")
        with mock.patch.object(social, "update_readme"):
            self.assertIn("Nothing new", social.share(self.pet, NOON, push=True))
        self.assertEqual(self.git("rev-list", "--count", "HEAD"), count)

    def test_share_refuses_other_repos(self):
        for url in ("https://github.com/me/terminal-tamagotchi.git", "https://gitlab.com/me/me.git", "/some/path/me"):
            self.git("remote", "set-url", "origin", url)
            with self.assertRaises(hooks.HookError, msg=url):
                social.share(self.pet, NOON)
        self.assertFalse((self.repo / "pet.json").exists())

    def test_share_accepts_ssh_and_mixed_case_urls(self):
        for url in ("git@github.com:me/me.git", "https://github.com/Me/me", "https://github.com/me/ME.git"):
            self.git("remote", "set-url", "origin", url)
            self.assertEqual(social.profile_repo(), self.repo.resolve())

    def test_failed_push_is_a_clear_error(self):
        self.git("remote", "set-url", "--push", "origin", "/no/such/remote")
        with self.assertRaises(hooks.HookError) as caught:
            social.share(self.pet, NOON, push=True)
        self.assertIn("git failed", str(caught.exception))

    def test_workflow_has_what_it_needs(self):
        self.assertIn("cron:", social.WORKFLOW)
        self.assertIn("contents: write", social.WORKFLOW)
        self.assertIn("pet profile-update", social.WORKFLOW)
        self.assertNotIn("\t", social.WORKFLOW)


class FriendsTest(TempFilesTest):
    def test_add_and_remove(self):
        self.assertIn("Added", social.add_friend("octocat"))
        self.assertIn("already", social.add_friend("OctoCat"))
        self.assertEqual(social.read_friends(), ["octocat"])
        self.assertIn("Removed", social.remove_friend("OCTOCAT"))
        self.assertIn("wasn't", social.remove_friend("octocat"))
        self.assertEqual(social.read_friends(), [])

    def test_unsafe_usernames_are_refused(self):
        for name in ("", None, "a/b", "../x", "a b", "a?b", "-dash", "x" * 40, "a\n", "evil.com#"):
            with self.assertRaises(hooks.HookError, msg=repr(name)):
                social.add_friend(name)
        self.assertEqual(social.read_friends(), [])

    def test_bad_friends_file_is_filtered(self):
        for content, expected in (("{broken", []), ('{"a": 1}', []), ('["good", "../bad", 5]', ["good"])):
            social.FRIENDS_PATH.write_text(content)
            self.assertEqual(social.read_friends(), expected, content)

    def test_leaderboard_ranks_by_xp(self):
        social.add_friend("rich")
        social.add_friend("poor")
        rich = social.from_snapshot(good_snapshot(name="Rich", xp=5000))
        poor = social.from_snapshot(good_snapshot(name="Poor", xp=5))
        with mock.patch.object(social, "fetch_friend", side_effect=lambda user, now: {"rich": rich, "poor": poor}[user]):
            rows = social.leaderboard({**pet_logic.new_pet(NOON), "xp": 100, "level": 2}, NOON).split("\n")
        self.assertEqual(len(rows), 3)
        self.assertIn("Rich (@rich)", rows[0])
        self.assertIn("Porky (you)", rows[1])
        self.assertIn("Poor (@poor)", rows[2])

    def test_missing_friends_are_listed_not_fatal(self):
        social.add_friend("ghost")
        with mock.patch.object(social, "fetch_friend", return_value=None):
            output = social.leaderboard(pet_logic.new_pet(NOON), NOON)
        self.assertIn("Porky (you)", output)
        self.assertIn("@ghost: no pet found", output)

    def test_no_friends_gets_a_hint(self):
        self.assertIn("pet friends add", social.leaderboard(pet_logic.new_pet(NOON), NOON))

    def test_cli_friends_commands(self):
        self.assertEqual(self.run_cli("friends", "add")[0], 1)
        self.assertEqual(self.run_cli("friends", "remove")[0], 1)
        self.assertEqual(self.run_cli("friends", "add", "octocat")[0], 0)
        with mock.patch.object(social, "fetch_friend", return_value=None):
            code, output, _ = self.run_cli("friends")
        self.assertEqual(code, 0)
        self.assertIn("@octocat", output)


class FetchTest(TempFilesTest):
    def serve(self, body):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(handler):
                handler.send_response(200)
                handler.end_headers()
                handler.wfile.write(body)

            def log_message(handler, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_port}/{{user}}"
        patcher = mock.patch.object(social, "SNAPSHOT_URL", url)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_fetch_applies_time_passed(self):
        self.serve(json.dumps(good_snapshot()).encode())
        self.assertEqual(social.fetch_friend("me", NOON + DAY)["hunger"], 3.5)

    def test_garbage_and_oversized_responses_mean_no_pet(self):
        deep = b"[" * 50000
        huge = json.dumps({**good_snapshot(), "padding": "x" * (social.MAX_SNAPSHOT_BYTES + 1)}).encode()
        for body in (b"not json", b"[]", b"\xff\xfe", b"", deep, huge):
            with self.subTest(body=body[:20]):
                self.serve(body)
                self.assertIsNone(social.fetch_friend("me", NOON))

    def test_certificates_are_always_verified(self):
        import ssl

        context = social.tls_context()
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)

    def test_server_error_means_no_pet(self):
        with mock.patch.object(social, "SNAPSHOT_URL", "http://127.0.0.1:1/{user}"):
            self.assertIsNone(social.fetch_friend("me", NOON))


class FaceTest(TempFilesTest):
    def test_face_prints_only_the_face(self):
        storage.save({**pet_logic.new_pet(NOON), "level": 1, "hunger": 5.0, "last_update": 4102444800})
        code, output, err = self.run_cli("face")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(len(output.strip().splitlines()), 1)
        self.assertLessEqual(len(output.strip()), 5)

    def test_face_stays_quiet_on_a_broken_save(self):
        storage.PATH.write_text(json.dumps({"hunger": "lots", "level": 1}))
        code, output, err = self.run_cli("face")
        self.assertEqual((code, output, err), (0, "", ""))

    def test_face_never_reads_claudes_logs(self):
        with mock.patch.object(claude, "tokens_today", side_effect=AssertionError):
            code, output, _ = self.run_cli("face")
        self.assertEqual(code, 0)
        self.assertTrue(output.strip())


if __name__ == "__main__":
    unittest.main()
