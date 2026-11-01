import contextlib
import io
import json
import os
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from tamagotchi import agent, art, claude, cli, pet as pet_logic, storage

DAY = pet_logic.SECONDS_PER_DAY
NOON = datetime(2026, 1, 15, 12).timestamp()


def log_line(message_id, input_tokens, output_tokens, when=NOON):
    stamp = datetime.fromtimestamp(when, timezone.utc).isoformat().replace("+00:00", "Z")
    usage = {"input_tokens": input_tokens, "output_tokens": output_tokens, "cache_read_input_tokens": 999999}
    return json.dumps({"timestamp": stamp, "message": {"id": message_id, "usage": usage}})


class TokensTodayTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "projects"
        self.root.mkdir()
        patcher = mock.patch.object(claude, "PROJECTS", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_log(self, *lines, name="session.jsonl"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def test_adds_input_and_output_but_not_cache(self):
        self.write_log(log_line("a", 10, 100), log_line("b", 5, 50))
        self.assertEqual(claude.tokens_today(NOON), 165)

    def test_only_counts_today(self):
        self.write_log(log_line("a", 0, 100), log_line("b", 0, 7, when=NOON - DAY))
        self.assertEqual(claude.tokens_today(NOON), 100)

    def test_repeated_message_counts_once_using_the_last_entry(self):
        self.write_log(log_line("a", 0, 10), log_line("a", 0, 10), log_line("a", 0, 300))
        self.assertEqual(claude.tokens_today(NOON), 300)

    def test_same_message_in_two_logs_counts_once(self):
        self.write_log(log_line("a", 0, 100), name="one.jsonl")
        self.write_log(log_line("a", 0, 100), name="sub/two.jsonl")
        self.assertEqual(claude.tokens_today(NOON), 100)

    def test_old_files_are_skipped_without_being_read(self):
        path = self.write_log(log_line("a", 0, 100))
        os.utime(path, (NOON - 2 * DAY, NOON - 2 * DAY))
        with mock.patch.object(claude, "message_tokens") as parse:
            self.assertEqual(claude.tokens_today(NOON), 0)
        parse.assert_not_called()

    def test_junk_lines_are_ignored(self):
        self.write_log(
            '{"usage": broken',
            '"usage"',
            json.dumps({"usage": "a chat message that mentions usage"}),
            json.dumps({"timestamp": "not a date", "message": {"id": "x", "usage": {}}}),
            json.dumps({"timestamp": "2026-01-15T12:00:00Z", "message": {"id": "y", "usage": {"input_tokens": "lots"}}}),
            json.dumps({"timestamp": 5, "message": "usage"}),
            log_line("a", 0, 100),
        )
        self.assertEqual(claude.tokens_today(NOON), 100)

    def test_no_logs_folder_means_zero(self):
        with mock.patch.object(claude, "PROJECTS", self.root / "missing"):
            self.assertEqual(claude.tokens_today(NOON), 0)


class TokenDisplayTest(unittest.TestCase):
    def hatched_pet(self):
        pet = pet_logic.new_pet(NOON)
        pet["level"] = 1
        return pet

    def test_format_tokens(self):
        cases = {0: "0", 999: "999", 1000: "1k", 412345: "412k", 999999: "999k", 1000000: "1.0M", 1300000: "1.3M"}
        for tokens, text in cases.items():
            self.assertEqual(art.format_tokens(tokens), text)

    def test_line_only_shows_when_there_are_tokens(self):
        pet = self.hatched_pet()
        self.assertNotIn("tokens today", art.render(pet, "content"))
        self.assertIn("🤖 412k tokens today", art.render(pet, "content", tokens=412000))

    def test_token_line_fits_every_form(self):
        for level in (0, 1, 5, 10):
            pet = self.hatched_pet()
            pet["level"] = level
            self.assertIn("tokens today", art.render(pet, "content", tokens=5000))

    def test_heavy_day_makes_it_wired(self):
        pet = self.hatched_pet()
        heavy = pet_logic.HEAVY_TOKENS
        self.assertEqual(pet_logic.feeling(pet, NOON, heavy - 1), "content")
        self.assertEqual(pet_logic.feeling(pet, NOON, heavy), "wired")

    def test_being_hungry_outranks_being_wired(self):
        pet = self.hatched_pet()
        pet["hunger"] = 2.0
        self.assertEqual(pet_logic.feeling(pet, NOON, pet_logic.HEAVY_TOKENS), "hungry")

    def test_eggs_dont_get_wired(self):
        pet = pet_logic.new_pet(NOON)
        self.assertEqual(pet_logic.feeling(pet, NOON, pet_logic.HEAVY_TOKENS), "egg")


class WeeklyLimitTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        folder = Path(tmp.name)
        self.limit_path = folder / "limit.json"
        self.pet_path = folder / "pet.json"
        for target, attribute, value in (
            (claude, "LIMIT_PATH", self.limit_path),
            (claude, "PROJECTS", folder / "no-logs"),
            (agent, "AGENT_PATH", folder / "agent.json"),
            (storage, "PATH", self.pet_path),
        ):
            patcher = mock.patch.object(target, attribute, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def status(self, used, resets_at=NOON + DAY):
        return {"rate_limits": {"seven_day": {"used_percentage": used, "resets_at": resets_at}}}

    def run_statusline(self, stdin):
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(stdin)), contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["statusline"]), 0)
        return out.getvalue()

    def test_saves_and_reads_the_limit(self):
        claude.save_limit(self.status(85.5))
        self.assertEqual(claude.weekly_limit(NOON), (85.5, DAY))

    def test_limit_is_forgotten_after_the_reset(self):
        claude.save_limit(self.status(100))
        self.assertIsNone(claude.weekly_limit(NOON + DAY))

    def test_status_without_limits_keeps_the_last_known_value(self):
        claude.save_limit(self.status(50))
        for status in ({}, {"rate_limits": None}, {"rate_limits": {"five_hour": {"used_percentage": 9}}}):
            claude.save_limit(status)
        self.assertEqual(claude.weekly_limit(NOON)[0], 50)

    def test_unreadable_limit_file_means_unknown(self):
        self.assertIsNone(claude.weekly_limit(NOON))
        for content in ("{broken", "[]", '{"used": "lots", "resets_at": 5}', '{"used": 5}'):
            self.limit_path.write_text(content)
            self.assertIsNone(claude.weekly_limit(NOON), content)

    def test_feelings_at_each_threshold(self):
        pet = pet_logic.new_pet(NOON)
        pet["level"] = 1
        for used, expected in ((79.9, "content"), (80, "nervous"), (99.9, "nervous"), (100, "dead")):
            self.assertEqual(pet_logic.feeling(pet, NOON, limit_used=used), expected)

    def test_dead_outranks_a_level_up_but_nervous_doesnt(self):
        pet = pet_logic.new_pet(NOON)
        pet_logic.feed(pet, NOON)
        self.assertEqual(pet_logic.feeling(pet, NOON, limit_used=100), "dead")
        self.assertEqual(pet_logic.feeling(pet, NOON, limit_used=90), "ecstatic")

    def test_eggs_cant_die(self):
        pet = pet_logic.new_pet(NOON)
        self.assertEqual(pet_logic.feeling(pet, NOON, limit_used=100), "egg")

    def test_limit_never_changes_stats(self):
        storage.save({**pet_logic.new_pet(time.time()), "level": 3, "xp": 200})
        before = self.pet_path.read_text()
        self.run_statusline(json.dumps(self.status(100, time.time() + DAY)))
        self.assertEqual(self.pet_path.read_text(), before)

    def test_format_limit(self):
        self.assertEqual(art.format_limit((99.6, 5 * 3600)), "99% of weekly limit, resets in 5h")
        self.assertEqual(art.format_limit((80, 3 * DAY)), "80% of weekly limit, resets in 3d")

    def test_statusline_shows_the_limit(self):
        storage.save({**pet_logic.new_pet(time.time()), "level": 3})
        output = self.run_statusline(json.dumps(self.status(100, time.time() + DAY)))
        self.assertIn("x _ x", output)
        self.assertIn("100% of weekly limit", output)

    def test_statusline_stays_quiet_on_bad_input(self):
        for stdin in ("", "{broken", "[]", '{"rate_limits": 5}'):
            self.assertEqual(self.run_statusline(stdin), "", stdin)

    def test_full_pet_shows_the_limit_row_in_every_form(self):
        for level in (0, 1, 5, 10):
            pet = pet_logic.new_pet(NOON)
            pet["level"] = level
            self.assertIn("⏳ 85% of weekly limit", art.render(pet, "nervous", limit=(85, DAY), tokens=5000))


if __name__ == "__main__":
    unittest.main()
