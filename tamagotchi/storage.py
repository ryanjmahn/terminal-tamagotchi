import json
import os
import sys
from pathlib import Path

PATH = Path.home() / ".terminal-tamagotchi" / "pet.json"


def load():
    """Return the saved pet, or None if there isn't a readable one."""
    try:
        pet = json.loads(PATH.read_text(encoding="utf-8"))
        if isinstance(pet, dict):
            return pet
    except FileNotFoundError:
        return None
    except ValueError:
        pass
    # Keep the damaged file so a bad save never silently destroys a pet.
    backup = PATH.with_name(PATH.name + ".corrupt")
    os.replace(PATH, backup)
    print(f"warning: couldn't read your save file, moved it to {backup}", file=sys.stderr)
    return None


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write then swap, so a crash mid-write can't leave a half-written save.
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def save(pet):
    write_json(PATH, pet)
