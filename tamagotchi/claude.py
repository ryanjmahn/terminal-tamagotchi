import json
from datetime import date, datetime
from pathlib import Path

from tamagotchi import storage

PROJECTS = Path.home() / ".claude" / "projects"
LIMIT_PATH = Path.home() / ".terminal-tamagotchi" / "limit.json"


def save_limit(status):
    """Remember the weekly limit from the JSON Claude Code gives a status line, when it's included."""
    weekly = (status.get("rate_limits") or {}).get("seven_day") or {}
    if "used_percentage" in weekly and "resets_at" in weekly:
        storage.write_json(LIMIT_PATH, {"used": weekly["used_percentage"], "resets_at": weekly["resets_at"]})


def weekly_limit(now):
    """Return (percent used, seconds until reset), or None if unknown or the window has reset."""
    try:
        saved = json.loads(LIMIT_PATH.read_text(encoding="utf-8"))
        used, seconds_left = float(saved["used"]), float(saved["resets_at"]) - now
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return (used, seconds_left) if seconds_left > 0 else None


def message_tokens(line, today):
    """Return (message id, tokens) if this log line is a message from today, otherwise None."""
    try:
        entry = json.loads(line)
        message = entry["message"]
        usage = message["usage"]
        stamp = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00")).timestamp()
        if date.fromtimestamp(stamp) != today:
            return None
        # Cached tokens are left out: they're mostly context being re-read, and they dwarf real work.
        return message["id"], int(usage["input_tokens"]) + int(usage["output_tokens"])
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError, OSError):
        return None


def tokens_today(now):
    """Claude Code tokens used on the local calendar day of `now`, or 0 if there's nothing readable.

    These logs aren't an official interface and they hold full conversations, so any
    surprise just means 0, and only the id, timestamp and token counts are ever used.
    """
    today = date.fromtimestamp(now)
    messages = {}
    for path in PROJECTS.rglob("*.jsonl"):
        try:
            if date.fromtimestamp(path.stat().st_mtime) < today:
                continue
            with path.open(encoding="utf-8", errors="replace") as log:
                for line in log:
                    if '"usage"' in line:
                        found = message_tokens(line, today)
                        if found:
                            # Logs repeat a message as it streams, so the last entry for an id wins.
                            messages[found[0]] = found[1]
        except OSError:
            continue
    return sum(messages.values())
