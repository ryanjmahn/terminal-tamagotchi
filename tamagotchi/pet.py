from datetime import datetime

SECONDS_PER_DAY = 86400
# Full hunger reads ~3.5 hearts after 1 day and ~0.5 after 3 days.
HUNGER_PER_DAY = 1.5
MOOD_PER_DAY = 1


def new_pet(now):
    return {
        "name": "Byte",
        "hunger": 5.0,
        "mood": 3.0,
        "xp": 0,
        "level": 0,
        "streak": 0,
        "last_update": now,
    }


def decay(pet, now):
    """Apply the hunger and mood lost since the last update. `now` is a Unix timestamp."""
    # max(0, ...) so a clock moved backwards can't feed the pet.
    days = max(0, now - pet["last_update"]) / SECONDS_PER_DAY
    pet["hunger"] = max(0, pet["hunger"] - HUNGER_PER_DAY * days)
    pet["mood"] = max(0, pet["mood"] - MOOD_PER_DAY * days)
    pet["last_update"] = now


def feeling(pet, now):
    if 1 <= datetime.fromtimestamp(now).hour < 5:
        return "sleepy"
    if pet["hunger"] < 1 or pet["mood"] < 1:
        return "sad"
    if pet["hunger"] <= 3.5:
        return "hungry"
    if pet["hunger"] >= 4 and pet["mood"] >= 4:
        return "happy"
    return "content"
