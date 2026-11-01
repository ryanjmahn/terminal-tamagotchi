import contextlib
import io
import json
import tempfile
import unicodedata
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from tamagotchi import agent, art, claude, cli, hooks, pet as pet_logic, storage

NOON = datetime(2026, 1, 15, 12).timestamp()
# Kept before setUp swaps in a recorder, so tests never pop up real notifications.
REAL_PING = agent.ping


class TempFilesTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)
        self.settings = self.folder / "claude" / "settings.json"
        self.agent_path = self.folder / "agent.json"
        self.pings = []
        for target, attribute, value in (
            (agent, "AGENT_PATH", self.agent_path),
            (agent, "SETTINGS_PATH", self.settings),
            (agent, "ping", self.pings.append),
            (claude, "PROJECTS", self.folder / "no-logs"),
            (claude, "LIMIT_PATH", self.folder / "limit.json"),
            (storage, "PATH", self.folder / "pet.json"),
        ):
            patcher = mock.patch.object(target, attribute, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def event(self, name, now=NOON, session="one", **fields):
        agent.handle({"hook_event_name": name, "session_id": session, **fields}, now)


class AgentStateTest(TempFilesTest):
    def test_no_run_means_no_status(self):
        self.assertIsNone(agent.status(NOON))

    def test_a_prompt_starts_a_run_and_tools_are_counted(self):
        self.event("UserPromptSubmit")
        self.event("PostToolUse", NOON + 30)
        self.event("PostToolUseFailure", NOON + 60)
        self.assertEqual(agent.status(NOON + 60), {"state": "working", "tools": 2, "seconds": 60})

    def test_a_new_prompt_starts_counting_again(self):
        self.event("UserPromptSubmit")
        self.event("PostToolUse")
        self.event("UserPromptSubmit", NOON + 10)
        self.assertEqual(agent.status(NOON + 10)["tools"], 0)

    def test_long_runs_become_looping(self):
        self.event("UserPromptSubmit")
        for _ in range(agent.LOOP_TOOLS - 1):
            self.event("PostToolUse")
        self.assertEqual(agent.status(NOON)["state"], "working")
        self.event("PostToolUse")
        self.assertEqual(agent.status(NOON)["state"], "looping")

    def test_slow_runs_become_looping_even_with_few_tools(self):
        self.event("UserPromptSubmit")
        later = NOON + agent.LOOP_SECONDS
        self.event("PostToolUse", later)
        self.assertEqual(agent.status(later)["state"], "looping")

    def test_approval_prompt_waits_and_pings(self):
        self.event("UserPromptSubmit")
        self.event("Notification", notification_type="permission_prompt")
        self.assertEqual(agent.status(NOON)["state"], "waiting")
        self.assertEqual(len(self.pings), 1)
        self.assertIn("approval", self.pings[0])

    def test_other_notifications_are_ignored(self):
        self.event("UserPromptSubmit")
        self.event("Notification", notification_type="idle_prompt")
        self.assertEqual(agent.status(NOON)["state"], "working")
        self.assertEqual(self.pings, [])

    def test_tool_running_clears_waiting(self):
        self.event("UserPromptSubmit")
        self.event("Notification", notification_type="permission_prompt")
        self.event("PostToolUse", NOON + 5)
        self.assertEqual(agent.status(NOON + 5)["state"], "working")

    def test_finished_keeps_the_final_time(self):
        self.event("UserPromptSubmit")
        self.event("Stop", NOON + 90)
        status = agent.status(NOON + 500)
        self.assertEqual((status["state"], status["seconds"]), ("finished", 90))

    def test_only_long_runs_ping_when_finished(self):
        self.event("UserPromptSubmit")
        self.event("Stop", NOON + agent.LONG_RUN_SECONDS - 1)
        self.assertEqual(self.pings, [])
        self.event("UserPromptSubmit", NOON)
        self.event("Stop", NOON + agent.LONG_RUN_SECONDS)
        self.assertEqual(len(self.pings), 1)

    def test_states_expire(self):
        self.event("UserPromptSubmit")
        self.assertIsNone(agent.status(NOON + agent.EXPIRES_AFTER["working"]))
        self.event("Stop")
        self.assertIsNotNone(agent.status(NOON + agent.EXPIRES_AFTER["finished"] - 1))
        self.assertIsNone(agent.status(NOON + agent.EXPIRES_AFTER["finished"]))

    def test_session_end_clears_only_its_own_session(self):
        self.event("UserPromptSubmit", session="one")
        self.event("SessionEnd", session="other")
        self.assertIsNotNone(agent.status(NOON))
        self.event("SessionEnd", session="one")
        self.assertFalse(self.agent_path.exists())

    def test_prompts_and_tool_output_are_never_saved(self):
        self.event("UserPromptSubmit", prompt="my secret plan")
        self.event("PostToolUse", tool_input={"command": "my secret plan"}, tool_response="my secret plan")
        self.event("Stop", last_assistant_message="my secret plan")
        self.assertNotIn("secret", self.agent_path.read_text())

    def test_unreadable_state_means_no_status(self):
        for content in ("{broken", "[]", "{}", '{"state": "nonsense", "tools": 1, "updated": 1, "started": 1}'):
            self.agent_path.write_text(content)
            self.assertIsNone(agent.status(NOON), content)

    def test_agent_event_is_silent_and_never_fails(self):
        for stdin in ("", "{broken", "[]", "{}", '{"hook_event_name": "UserPromptSubmit", "session_id": "a"}'):
            out = io.StringIO()
            with mock.patch("sys.stdin", io.StringIO(stdin)), contextlib.redirect_stdout(out):
                self.assertEqual(cli.main(["agent-event"]), 0, stdin)
            self.assertEqual(out.getvalue(), "", stdin)

    def test_ping_passes_the_message_safely(self):
        with mock.patch("subprocess.run") as run:
            REAL_PING('quote " and $(rm -rf x)')
        args = run.call_args[0][0]
        self.assertEqual(args[0], "osascript")
        self.assertEqual(args[-1], 'quote " and $(rm -rf x)')
        self.assertFalse(run.call_args[1].get("shell"))


class FeelingTest(unittest.TestCase):
    def pet(self):
        return {**pet_logic.new_pet(NOON), "level": 1}

    def test_each_state_has_its_feeling(self):
        pet = self.pet()
        self.assertEqual(pet_logic.feeling(pet, NOON, agent_state="waiting"), "waiting")
        self.assertEqual(pet_logic.feeling(pet, NOON, agent_state="looping"), "looping")
        self.assertEqual(pet_logic.feeling(pet, NOON, agent_state="finished"), "finished")
        self.assertEqual(pet_logic.feeling(pet, NOON, agent_state="working"), "content")

    def test_dead_outranks_waiting_and_waiting_outranks_a_level_up(self):
        pet = self.pet()
        pet["leveled_at"] = NOON
        self.assertEqual(pet_logic.feeling(pet, NOON, limit_used=100, agent_state="waiting"), "dead")
        self.assertEqual(pet_logic.feeling(pet, NOON, agent_state="waiting"), "waiting")

    def test_eggs_stay_eggs(self):
        pet = pet_logic.new_pet(NOON)
        self.assertEqual(pet_logic.feeling(pet, NOON, agent_state="waiting"), "egg")


class SettingsTest(TempFilesTest):
    def read(self):
        return json.loads(self.settings.read_text())

    def write(self, data):
        self.settings.parent.mkdir(exist_ok=True)
        self.settings.write_text(json.dumps(data))

    def ours(self, settings):
        return [
            handler["command"]
            for groups in settings.get("hooks", {}).values()
            for group in groups
            for handler in group["hooks"]
            if agent.COMMAND in handler["command"]
        ]

    def test_install_creates_settings_when_missing(self):
        agent.install("/py/python")
        settings = self.read()
        self.assertEqual(set(settings["hooks"]), set(agent.EVENTS))
        self.assertEqual(settings["hooks"]["Notification"][0]["matcher"], "permission_prompt")
        self.assertEqual(settings["hooks"]["Stop"][0]["hooks"][0]["command"], f"/py/python {agent.COMMAND}")

    def test_install_keeps_everything_else(self):
        mine = {"matcher": "Bash", "hooks": [{"type": "command", "command": "my-script"}]}
        self.write({"effortLevel": "high", "hooks": {"PostToolUse": [mine], "PreToolUse": [mine]}, "attribution": {"a": 1}})
        agent.install("/py/python")
        settings = self.read()
        self.assertEqual(settings["effortLevel"], "high")
        self.assertEqual(settings["attribution"], {"a": 1})
        self.assertEqual(settings["hooks"]["PreToolUse"], [mine])
        self.assertEqual(settings["hooks"]["PostToolUse"][0], mine)
        self.assertEqual(len(settings["hooks"]["PostToolUse"]), 2)

    def test_install_twice_keeps_one_copy(self):
        agent.install("/old/python")
        agent.install("/new/python")
        commands = self.ours(self.read())
        self.assertEqual(len(commands), len(agent.EVENTS))
        self.assertTrue(all(c.startswith("/new/python") for c in commands))

    def test_uninstall_restores_the_original_settings(self):
        mine = {"matcher": "Bash", "hooks": [{"type": "command", "command": "my-script"}]}
        original = {"effortLevel": "high", "hooks": {"PostToolUse": [mine]}}
        self.write(original)
        agent.install("/py/python")
        agent.uninstall()
        self.assertEqual(self.read(), original)

    def test_uninstall_removes_the_section_if_it_was_only_ours(self):
        self.write({"effortLevel": "high"})
        agent.install("/py/python")
        agent.uninstall()
        self.assertEqual(self.read(), {"effortLevel": "high"})

    def test_uninstall_when_not_installed_changes_nothing(self):
        self.write({"effortLevel": "high"})
        before = self.settings.read_text()
        self.assertIn("isn't installed", agent.uninstall())
        self.assertEqual(self.settings.read_text(), before)

    def test_bad_settings_are_refused_and_untouched(self):
        self.settings.parent.mkdir()
        for content in ("{broken", "[]", '{"hooks": []}', '{"hooks": {"Stop": [5]}}', '{"hooks": {"Stop": 5}}'):
            self.settings.write_text(content)
            with self.assertRaises(hooks.HookError, msg=content):
                agent.install("/py/python")
            self.assertEqual(self.settings.read_text(), content)

    def test_file_permissions_are_kept(self):
        self.write({"env": {"SECRET": "x"}})
        self.settings.chmod(0o600)
        agent.install("/py/python")
        self.assertEqual(self.settings.stat().st_mode & 0o777, 0o600)

    def test_symlinked_settings_stay_a_symlink(self):
        real = self.folder / "dotfiles.json"
        real.write_text("{}")
        self.settings.parent.mkdir()
        self.settings.symlink_to(real)
        agent.install("/py/python")
        self.assertTrue(self.settings.is_symlink())
        self.assertIn("hooks", json.loads(real.read_text()))


class AnimationTest(TempFilesTest):
    def test_every_frame_fills_nine_cells(self):
        for feeling, faces in art.ALT_FACES.items():
            self.assertIn(feeling, art.FACES)
            for face in faces:
                cells = sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in face)
                self.assertEqual(cells, 9, f"{feeling}: {face}")

    def test_every_new_feeling_has_lines(self):
        for feeling in art.FACES:
            self.assertIn(feeling, art.LINES)

    def test_frames_change_the_face_and_loop(self):
        pet = {**pet_logic.new_pet(NOON), "level": 1}
        kwargs = {"line": "hi"}
        self.assertIn("• ‿ •", art.render(pet, "content", frame=0, **kwargs))
        self.assertIn("- ‿ -", art.render(pet, "content", frame=3, **kwargs))
        self.assertEqual(art.render(pet, "content", frame=0, **kwargs), art.render(pet, "content", frame=4, **kwargs))

    def test_dead_pets_dont_move(self):
        pet = {**pet_logic.new_pet(NOON), "level": 1}
        frames = {art.render(pet, "dead", frame=i, line="x") for i in range(6)}
        self.assertEqual(len(frames), 1)

    def test_wiggling_never_moves_the_stats(self):
        for level in (0, 1, 5, 10):
            pet = {**pet_logic.new_pet(NOON), "level": level}
            still = art.render(pet, "ecstatic", frame=0, line="x").split("\n")
            moved = art.render(pet, "ecstatic", frame=1, line="x").split("\n")
            self.assertNotEqual(still, moved)
            row = next(i for i, text in enumerate(still) if "hunger" in text)
            self.assertEqual(still[row].index("♥"), moved[row].index("♥"))

    def test_play_ends_on_the_normal_face_and_restores_the_cursor(self):
        pet = {**pet_logic.new_pet(NOON), "level": 1}
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch("time.sleep"):
            art.play(lambda frame: art.render(pet, "content", frame=frame, line="x"))
        output = out.getvalue()
        self.assertTrue(output.endswith("\033[?25h"))
        self.assertGreater(output.rfind("• ‿ •"), output.rfind("- ‿ -"))

    def test_play_restores_the_cursor_when_interrupted(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch("time.sleep", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                art.play(lambda frame: "x")
        self.assertTrue(out.getvalue().endswith("\033[?25h"))

    def test_watch_without_a_terminal_prints_once(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["watch"]), 0)
        self.assertNotIn("\033[", out.getvalue())
        self.assertIn("hunger", out.getvalue())

    def test_watch_restores_the_terminal_on_ctrl_c(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.object(art, "can_animate", return_value=True):
            with mock.patch("time.sleep", side_effect=[None, None, KeyboardInterrupt]):
                self.assertEqual(cli.main(["watch"]), 0)
        self.assertTrue(out.getvalue().endswith("\033[?25h\033[?1049l"))

    def test_watch_shows_claude_live(self):
        self.event("UserPromptSubmit", NOON)
        with mock.patch.object(agent, "status", return_value={"state": "waiting", "tools": 1, "seconds": 5}):
            out = io.StringIO()
            with contextlib.redirect_stdout(out), mock.patch.object(art, "can_animate", return_value=True):
                with mock.patch("time.sleep", side_effect=KeyboardInterrupt):
                    cli.main(["watch"])
        self.assertIn("claude needs your approval!", out.getvalue())

    def test_format_agent(self):
        status = {"tools": 23, "seconds": 245}
        self.assertEqual(art.format_agent({**status, "state": "working"}), "claude is working (23 tools, 4m)")
        self.assertEqual(art.format_agent({**status, "state": "finished"}), "claude finished (23 tools, 4m)")
        self.assertEqual(art.format_duration(30), "30s")
        self.assertEqual(art.format_duration(3900), "1h 5m")


if __name__ == "__main__":
    unittest.main()
