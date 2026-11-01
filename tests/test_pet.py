import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from tamagotchi import pet as pet_logic, storage

DAY = pet_logic.SECONDS_PER_DAY
NOON = datetime(2026, 1, 1, 12).timestamp()


class DecayTest(unittest.TestCase):
    def after(self, days):
        pet = pet_logic.new_pet(NOON)
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
        pet = pet_logic.new_pet(NOON)
        for hour in range(1, 25):
            pet_logic.decay(pet, NOON + hour * 3600)
        self.assertAlmostEqual(pet["hunger"], 3.5)


class FeelingTest(unittest.TestCase):
    def test_sleepy_only_between_1am_and_5am(self):
        pet = pet_logic.new_pet(NOON)
        at = lambda hour: datetime(2026, 1, 1, hour).timestamp()
        self.assertEqual(pet_logic.feeling(pet, at(0)), "content")
        self.assertEqual(pet_logic.feeling(pet, at(1)), "sleepy")
        self.assertEqual(pet_logic.feeling(pet, at(4)), "sleepy")
        self.assertEqual(pet_logic.feeling(pet, at(5)), "content")


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


if __name__ == "__main__":
    unittest.main()
