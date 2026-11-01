import json
import shlex
import subprocess
from pathlib import Path

from tamagotchi import hooks, storage

AGENT_PATH = Path.home() / ".terminal-tamagotchi" / "agent.json"
SETTINGS_PATH = Path.home() / ".claude" / "settings.json"
COMMAND = "-m tamagotchi.cli agent-event"
# Event name -> matcher. Tool events keep the run's progress, the rest change its state.
EVENTS = {
    "UserPromptSubmit": None,
    "PostToolUse": None,
    "PostToolUseFailure": None,
    "Notification": "permission_prompt",
    "Stop": None,
    "SessionEnd": None,
}
# About 1 run in 100 of real usage goes past these.
LOOP_TOOLS = 75
LOOP_SECONDS = 20 * 60
# About 1 run in 10 goes past this, so short answers don't ping you.
LONG_RUN_SECONDS = 5 * 60
# Events can go missing (say, if you interrupt Claude), so states expire instead of sticking forever.
EXPIRES_AFTER = {"working": 15 * 60, "waiting": 30 * 60, "finished": 10 * 60}


def ping(message):
    # shortcut: macOS only, other platforms just skip the ping. Add notify-send for Linux when needed.
    script = ["-e", "on run argv", "-e", 'display notification (item 1 of argv) with title "Terminal Tamagotchi"', "-e", "end run"]
    try:
        subprocess.run(["osascript", *script, message], capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        pass


def pet_name():
    return (storage.load() or {}).get("name", "Porky")


def read_state():
    try:
        return json.loads(AGENT_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def handle(event, now):
    """Update the agent state from a Claude Code hook event.

    Events can include your prompts and tool output, so only the event name,
    session id and notification type are read, and none of the rest is saved.
    """
    # shortcut: tracks one session at a time, so the latest active session wins. Key by session if that gets confusing.
    name, session = event["hook_event_name"], event.get("session_id")
    state = read_state()
    if name == "SessionEnd":
        if state.get("session") == session:
            AGENT_PATH.unlink(missing_ok=True)
        return
    if name == "UserPromptSubmit" or state.get("session") != session:
        state = {"session": session, "state": "working", "tools": 0, "started": now}

    if name in ("PostToolUse", "PostToolUseFailure"):
        state["state"] = "working"
        state["tools"] += 1
    elif name == "Notification":
        if event.get("notification_type") != "permission_prompt":
            return
        state["state"] = "waiting"
        ping(f"{pet_name()}: claude needs your approval!")
    elif name == "Stop":
        state["state"] = "finished"
        if now - state["started"] >= LONG_RUN_SECONDS:
            ping(f"{pet_name()}: claude finished! yay!")
    state["updated"] = now
    storage.write_json(AGENT_PATH, state)


def status(now):
    """Return {"state", "tools", "seconds"} for the current Claude run, or None if there isn't one."""
    try:
        saved = read_state()
        state, tools = saved["state"], saved["tools"]
        if now - saved["updated"] >= EXPIRES_AFTER[state]:
            return None
        seconds = (saved["updated"] if state == "finished" else now) - saved["started"]
    except (KeyError, TypeError):
        return None
    if state == "working" and (tools >= LOOP_TOOLS or seconds >= LOOP_SECONDS):
        state = "looping"
    return {"state": state, "tools": tools, "seconds": seconds}


def read_settings():
    try:
        settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except ValueError:
        raise hooks.HookError(f"{SETTINGS_PATH} isn't valid JSON, so I won't touch it. Nothing changed.")
    if not isinstance(settings, dict) or not isinstance(settings.get("hooks", {}), dict):
        raise hooks.HookError(f"{SETTINGS_PATH} has an unexpected layout, so I won't touch it. Nothing changed.")
    return settings


def write_settings(settings):
    # Resolving keeps a symlinked settings file (like one in a dotfiles repo) a symlink.
    path = SETTINGS_PATH.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(mode=0o644, exist_ok=True)
    hooks.write_hook(path, json.dumps(settings, indent=2, ensure_ascii=False) + "\n")


def without_our_hooks(settings):
    """Return the hooks section with ours removed and everything else left as it was."""
    cleaned = {}
    for event, groups in settings.get("hooks", {}).items():
        kept = []
        for group in groups:
            handlers = [h for h in group.get("hooks", []) if COMMAND not in h.get("command", "")]
            if handlers or not group.get("hooks"):
                kept.append({**group, "hooks": handlers})
        if kept:
            cleaned[event] = kept
    return cleaned


def install(python):
    settings = read_settings()
    try:
        cleaned = without_our_hooks(settings)
    except (AttributeError, TypeError):
        raise hooks.HookError(f"{SETTINGS_PATH} has an unexpected layout, so I won't touch it. Nothing changed.")
    for event, matcher in EVENTS.items():
        group = {"hooks": [{"type": "command", "command": f"{shlex.quote(python)} {COMMAND}"}]}
        if matcher:
            group = {"matcher": matcher, **group}
        cleaned.setdefault(event, []).append(group)
    settings["hooks"] = cleaned
    write_settings(settings)
    return (
        "Coding agent mode is on! Restart Claude Code, then try `pet watch`.\n"
        f"  settings: {SETTINGS_PATH}"
    )


def uninstall():
    settings = read_settings()
    try:
        cleaned = without_our_hooks(settings)
    except (AttributeError, TypeError):
        raise hooks.HookError(f"{SETTINGS_PATH} has an unexpected layout, so I won't touch it. Nothing changed.")
    if cleaned == settings.get("hooks", {}):
        return "Coding agent mode isn't installed, so there's nothing to remove."
    if cleaned:
        settings["hooks"] = cleaned
    else:
        del settings["hooks"]
    write_settings(settings)
    AGENT_PATH.unlink(missing_ok=True)
    return "Coding agent mode is off, and the rest of your settings are unchanged."
