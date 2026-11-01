from datetime import date, datetime

SECONDS_PER_DAY = 86400
# Full hunger reads ~3.5 hearts after 1 day and ~0.5 after 3 days.
HUNGER_PER_DAY = 1.5
MOOD_PER_DAY = 1
MAX_STAT = 5
# Commits bigger than this earn nothing extra, so 2000-line commits aren't worth it.
MAX_REWARDED_LINES = 200
ECSTATIC_SECONDS = 3600
# Claude Code tokens in a day that count as a heavy day. Only changes the face and line, never stats.
HEAVY_TOKENS = 250_000
# Percent of the weekly Claude limit. Also only the face and line, and it wears off at the reset.
NERVOUS_LIMIT = 80
DEAD_LIMIT = 100


def new_pet(now):
    return {
        "name": "Porky",
        "hunger": 5.0,
        "mood": 3.0,
        "xp": 0,
        "level": 0,
        "streak": 0,
        "last_fed": None,
        "leveled_at": None,
        "last_update": now,
    }


def days_since_fed(pet, now):
    if pet["last_fed"] is None:
        return None
    return (date.fromtimestamp(now) - date.fromisoformat(pet["last_fed"])).days


def decay(pet, now):
    """Apply the hunger and mood lost since the last update. `now` is a Unix timestamp."""
    # Eggs don't get hungry, so a pet you haven't hatched yet isn't punished.
    if pet["level"] > 0:
        # max(0, ...) so a clock moved backwards can't feed the pet.
        days = max(0, now - pet["last_update"]) / SECONDS_PER_DAY
        pet["hunger"] = max(0, pet["hunger"] - HUNGER_PER_DAY * days)
        pet["mood"] = max(0, pet["mood"] - MOOD_PER_DAY * days)
        gap = days_since_fed(pet, now)
        if gap is not None and gap > 1:
            pet["streak"] = 0
    pet["last_update"] = now


def level_for(xp):
    """Level 2 takes 50 XP, level 5 takes 500, level 10 takes 2250."""
    if xp <= 0:
        return 0
    level = 1
    while xp >= 25 * level * (level + 1):
        level += 1
    return level


def feed(pet, now, lines=0):
    """Give the pet a snack. Returns what happened: "hatched", "leveled" or "fed"."""
    decay(pet, now)
    size = min(max(lines, 0), MAX_REWARDED_LINES) / MAX_REWARDED_LINES
    mood_gain = 0.5

    gap = days_since_fed(pet, now)
    if gap == 1:
        pet["streak"] += 1
        mood_gain += 0.5
    elif gap is None or gap > 1:
        pet["streak"] = 1
    # A negative gap means the clock moved backwards, so keep the later date.
    if gap is None or gap > 0:
        pet["last_fed"] = date.fromtimestamp(now).isoformat()

    pet["hunger"] = min(MAX_STAT, pet["hunger"] + 1 + 0.5 * size)
    pet["mood"] = min(MAX_STAT, pet["mood"] + mood_gain)
    pet["xp"] += 10 + round(10 * size)

    old_level = pet["level"]
    pet["level"] = level_for(pet["xp"])
    if pet["level"] == old_level:
        return "fed"
    pet["leveled_at"] = now
    return "hatched" if old_level == 0 else "leveled"


def feeling(pet, now, tokens=0, limit_used=0, agent_state=None):
    if pet["level"] == 0:
        return "egg"
    if limit_used >= DEAD_LIMIT:
        return "dead"
    if agent_state == "waiting":
        return "waiting"
    if pet["leveled_at"] is not None and 0 <= now - pet["leveled_at"] < ECSTATIC_SECONDS:
        return "ecstatic"
    if limit_used >= NERVOUS_LIMIT:
        return "nervous"
    if agent_state in ("looping", "finished"):
        return agent_state
    if 1 <= datetime.fromtimestamp(now).hour < 5:
        return "sleepy"
    if pet["hunger"] < 1 or pet["mood"] < 1:
        return "sad"
    if pet["hunger"] <= 3.5:
        return "hungry"
    if tokens >= HEAVY_TOKENS:
        return "wired"
    if pet["hunger"] >= 4 and pet["mood"] >= 4:
        return "happy"
    return "content"
