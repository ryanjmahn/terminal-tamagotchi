import contextlib
import io
import tempfile
import unicodedata
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from tamagotchi import art, claude, cli, pet as pet_logic, storage

DAY = pet_logic.SECONDS_PER_DAY
NOON = datetime(2026, 1, 1, 12).timestamp()


def hatched_pet(now=NOON):
    pet = pet_logic.new_pet(now)
    pet["level"] = 1
    return pet


class DecayTest(unittest.TestCase):
    def after(self, days):
        pet = hatched_pet()
        pet_logic.decay(pet, NOON + days * DAY)
        return pet

    def test_noticeably_hungry_after_one_day(self):
        pet = self.after(1)
        self.assertEqual(pet["hunger"], 3.5)
        self.assertEqual(pet_logic.feeling(pet, NOON + DAY), "hungry")

    def test_very_hungry_after_three_days(self):
        pet = self.after(3)
        self.assertEqual(pet["hunger"], 0.5)
        self.assertEqual(pet_logic.feeling(pet, NOON + 3 * DAY), "sad")

    def test_stats_stop_at_zero(self):
        pet = self.after(100)
        self.assertEqual((pet["hunger"], pet["mood"]), (0, 0))

    def test_clock_moved_backwards_changes_nothing(self):
        pet = self.after(-5)
        self.assertEqual(pet["hunger"], 5)

    def test_running_often_decays_the_same_as_running_once(self):
        pet = hatched_pet()
        for hour in range(1, 25):
            pet_logic.decay(pet, NOON + hour * 3600)
        self.assertAlmostEqual(pet["hunger"], 3.5)

    def test_eggs_dont_get_hungry(self):
        pet = pet_logic.new_pet(NOON)
        pet_logic.decay(pet, NOON + 30 * DAY)
        self.assertEqual((pet["hunger"], pet["mood"]), (5, 3))


class FeedTest(unittest.TestCase):
    def test_first_feed_hatches_the_egg(self):
        pet = pet_logic.new_pet(NOON)
        self.assertEqual(pet_logic.feed(pet, NOON), "hatched")
        self.assertEqual(pet["level"], 1)
        self.assertEqual(pet_logic.feeling(pet, NOON), "ecstatic")

    def test_feeding_raises_hunger_but_not_past_full(self):
        pet = hatched_pet()
        pet["hunger"] = 2.0
        pet_logic.feed(pet, NOON)
        self.assertEqual(pet["hunger"], 3)
        pet["hunger"] = 4.5
        pet_logic.feed(pet, NOON)
        self.assertEqual(pet["hunger"], 5)

    def test_bigger_commits_give_more_but_are_capped(self):
        def xp_for(lines):
            pet = hatched_pet()
            pet_logic.feed(pet, NOON, lines)
            return pet["xp"]

        self.assertEqual(xp_for(0), 10)
        self.assertEqual(xp_for(100), 15)
        self.assertEqual(xp_for(200), 20)
        self.assertEqual(xp_for(5000), 20)
        self.assertEqual(xp_for(-5), 10)

    def test_feeding_raises_mood_but_not_past_the_top(self):
        pet = hatched_pet()
        pet_logic.feed(pet, NOON)
        self.assertEqual(pet["mood"], 3.5)
        pet["mood"] = 4.8
        pet_logic.feed(pet, NOON)
        self.assertEqual(pet["mood"], 5)

    def test_extending_a_streak_lifts_mood_extra(self):
        pet = hatched_pet()
        pet_logic.feed(pet, NOON)
        pet_logic.feed(pet, NOON + DAY)
        # 3.5 after the first snack, minus a day of decay, plus 0.5 and 0.5 for the streak.
        self.assertEqual(pet["mood"], 3.5)

    def test_ecstatic_wears_off(self):
        pet = pet_logic.new_pet(NOON)
        pet_logic.feed(pet, NOON)
        later = NOON + pet_logic.ECSTATIC_SECONDS
        self.assertNotEqual(pet_logic.feeling(pet, later), "ecstatic")


class LevelTest(unittest.TestCase):
    def test_thresholds(self):
        cases = {0: 0, 1: 1, 49: 1, 50: 2, 149: 2, 150: 3, 499: 4, 500: 5, 2249: 9, 2250: 10}
        for xp, level in cases.items():
            self.assertEqual(pet_logic.level_for(xp), level, f"xp={xp}")

    def test_level_up_is_reported(self):
        pet = hatched_pet()
        pet["xp"] = 45
        self.assertEqual(pet_logic.feed(pet, NOON), "leveled")
        self.assertEqual(pet["level"], 2)
        self.assertEqual(pet_logic.feed(pet, NOON), "fed")

    def test_each_form_appears_at_its_level(self):
        forms = {0: art.EGG, 1: art.BABY, 4: art.BABY, 5: art.TEEN, 9: art.TEEN, 10: art.ELDER}
        for level, form in forms.items():
            self.assertIs(art.form_for(level), form, f"level={level}")


class StreakTest(unittest.TestCase):
    def test_first_feed_starts_a_streak(self):
        pet = pet_logic.new_pet(NOON)
        pet_logic.feed(pet, NOON)
        self.assertEqual(pet["streak"], 1)

    def test_same_day_doesnt_extend(self):
        pet = pet_logic.new_pet(NOON)
        pet_logic.feed(pet, NOON)
        pet_logic.feed(pet, NOON + 3600)
        self.assertEqual(pet["streak"], 1)

    def test_next_day_extends_even_within_24_hours(self):
        late = datetime(2026, 1, 1, 23).timestamp()
        early = datetime(2026, 1, 2, 7).timestamp()
        pet = pet_logic.new_pet(late)
        pet_logic.feed(pet, late)
        pet_logic.feed(pet, early)
        self.assertEqual(pet["streak"], 2)

    def test_missed_day_restarts_on_next_feed(self):
        pet = pet_logic.new_pet(NOON)
        pet_logic.feed(pet, NOON)
        pet_logic.feed(pet, NOON + DAY)
        pet_logic.feed(pet, NOON + 3 * DAY)
        self.assertEqual(pet["streak"], 1)

    def test_missed_day_shows_as_broken_before_feeding(self):
        pet = pet_logic.new_pet(NOON)
        pet_logic.feed(pet, NOON)
        pet_logic.decay(pet, NOON + DAY)
        self.assertEqual(pet["streak"], 1)
        pet_logic.decay(pet, NOON + 2 * DAY)
        self.assertEqual(pet["streak"], 0)


class FeelingTest(unittest.TestCase):
    def test_sleepy_only_between_1am_and_5am(self):
        pet = hatched_pet()
        at = lambda hour: datetime(2026, 1, 1, hour).timestamp()
        self.assertEqual(pet_logic.feeling(pet, at(0)), "content")
        self.assertEqual(pet_logic.feeling(pet, at(1)), "sleepy")
        self.assertEqual(pet_logic.feeling(pet, at(4)), "sleepy")
        self.assertEqual(pet_logic.feeling(pet, at(5)), "content")


class ArtTest(unittest.TestCase):
    def test_faces_all_fill_nine_cells(self):
        for name, face in art.FACES.items():
            cells = sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in face)
            self.assertEqual(cells, 9, name)

    def test_every_form_and_feeling_renders(self):
        for level in (0, 1, 5, 10):
            for feeling in art.FACES:
                pet = pet_logic.new_pet(NOON)
                pet["level"] = level
                output = art.render(pet, feeling)
                self.assertIn(art.FACES[feeling], output)
                self.assertNotIn(art.FACE_SLOT, output)

    def test_every_event_has_lines(self):
        for event in ("hatched", "leveled", "fed"):
            self.assertIn(event, art.LINES)


class StorageTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "sub" / "pet.json"
        patcher = mock.patch.object(storage, "PATH", self.path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_missing_file_loads_as_none(self):
        self.assertIsNone(storage.load())

    def test_save_then_load(self):
        pet = pet_logic.new_pet(NOON)
        storage.save(pet)
        self.assertEqual(storage.load(), pet)

    def test_corrupt_file_is_kept_as_backup(self):
        self.path.parent.mkdir()
        self.path.write_text("{not json")
        with mock.patch("sys.stderr"):
            self.assertIsNone(storage.load())
        self.assertEqual(self.path.with_name("pet.json.corrupt").read_text(), "{not json")


class CliTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = mock.patch.object(storage, "PATH", Path(tmp.name) / "pet.json")
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(claude, "PROJECTS", Path(tmp.name) / "no-logs")
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(claude, "LIMIT_PATH", Path(tmp.name) / "limit.json")
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_feed_saves(self):
        self.run_cli("feed")
        self.assertEqual(storage.load()["level"], 1)

    def test_rename(self):
        code, output, _ = self.run_cli("name", "Mochi")
        self.assertEqual(code, 0)
        self.assertIn("Mochi", output)
        self.assertEqual(storage.load()["name"], "Mochi")

    def test_bad_names_are_refused(self):
        for name in ("", "   ", "x" * 21, "a\nb"):
            code, _, err = self.run_cli("name", name)
            self.assertEqual(code, 1, repr(name))
            self.assertIn("names must be", err)
        self.assertIsNone(storage.load())

    def test_reset_needs_confirmation(self):
        self.run_cli("feed")
        with mock.patch("builtins.input", return_value="n"):
            self.run_cli("reset")
        self.assertEqual(storage.load()["level"], 1)
        with mock.patch("builtins.input", side_effect=EOFError):
            self.run_cli("reset")
        self.assertEqual(storage.load()["level"], 1)
        with mock.patch("builtins.input", return_value="y"):
            self.run_cli("reset")
        self.assertEqual(storage.load()["level"], 0)


if __name__ == "__main__":
    unittest.main()
