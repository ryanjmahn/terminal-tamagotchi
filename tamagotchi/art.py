import math
import os
import random
import sys

COLOR = sys.stdout.isatty() and "NO_COLOR" not in os.environ and os.environ.get("TERM") != "dumb"
RED, YELLOW, CYAN, DIM = "31", "33", "36", "2"

# Each face fills 9 cells. ﹏ is double-width, so its faces get one less space.
FACES = {
    "happy": "  ◕ ‿ ◕  ",
    "content": "  • ‿ •  ",
    "hungry": "  • ﹏ • ",
    "sad": "  ╥ ﹏ ╥ ",
    "sleepy": "  - . -  ",
    "ecstatic": "  ★ ▽ ★  ",
    "wired": "  ◉ ‿ ◉  ",
    "nervous": "  ◉ ﹏ ◉ ",
    "dead": "  x _ x  ",
    "egg": "  · · ·  ",
}

# FACE_SLOT is exactly as wide as a face, so each row's length is its real width.
FACE_SLOT = "#########"
STATS_COLUMN = 17

EGG = [
    "      ╭─────╮",
    "     ╱  · ·  ╲",
    f"    │{FACE_SLOT}│",
    "     ╲       ╱",
    "      ╰─────╯",
]
BABY = [
    "   ╭─────────╮",
    f"   │{FACE_SLOT}│",
    "   ╰─┬─────┬─╯",
    "     ┘     └",
]
TEEN = [
    "    /\\     /\\",
    "   ╭─────────╮",
    f"   │{FACE_SLOT}│",
    "  /╰─┬─────┬─╯\\",
    "     ┘     └",
]
ELDER = [
    "      ▲ ▲ ▲",
    "   ╔══╧═╧═╧══╗",
    f"   ║{FACE_SLOT}║",
    "  /╚═╤═════╤═╝\\",
    "     ┘     └",
]

LINES = {
    "happy": ["life is good", "best. human. ever.", "*happy wiggle*"],
    "content": ["just vibing", "ship anything good today?", "*blinks at you*"],
    "hungry": ["...did you forget about me?", "a small commit would be nice", "*stomach rumbles*"],
    "sad": ["i have known only hunger", "remember when you used to commit?", "tell my story"],
    "sleepy": ["go to sleep bro 😴", "zzz... merge conflict... zzz", "it's so late, close the laptop"],
    "ecstatic": ["i feel POWERFUL", "look at me. LOOK AT ME.", "new level, same bugs"],
    "wired": ["did you and claude even sleep?", "that's a lot of tokens, are we ok", "claude's working hard. are you?"],
    "nervous": ["is it getting low in here or is it just me", "maybe... fewer tokens?", "*sweats in ASCII*"],
    "dead": ["here lies {name}. out of claude.", "tell claude i loved them", "wake me when the limit resets"],
    "egg": ["*wobbles*", "...tap tap... make a commit to hatch me", "🥚"],
    "fed": ["nom nom 🍪", "delicious diff", "tastes like clean code", "more please"],
    "hatched": ["{name} hatched!! hi!! who are you!!"],
    "leveled": ["{name} evolved!!"],
}


def paint(text, code):
    return f"\033[{code}m{text}\033[0m" if COLOR else text


def bar(value, full, empty):
    # Round up, so the last heart only disappears when the stat really hits 0.
    filled = math.ceil(value)
    return full * filled + empty * (5 - filled)


def form_for(level):
    if level == 0:
        return EGG
    if level < 5:
        return BABY
    if level < 10:
        return TEEN
    return ELDER


def reaction(pet, key):
    return random.choice(LINES[key]).format(name=pet["name"])


def format_tokens(tokens):
    if tokens < 1000:
        return str(tokens)
    if tokens < 1_000_000:
        return f"{tokens // 1000}k"
    return f"{tokens / 1_000_000:.1f}M"


def format_limit(limit):
    used, seconds_left = limit
    hours = int(seconds_left // 3600)
    left = f"{hours}h" if hours < 48 else f"{hours // 24}d"
    # Round down, so 99.6% doesn't read as 100% while the pet is still alive.
    return f"{int(used)}% of weekly limit, resets in {left}"


def render_statusline(pet, feeling, limit):
    face = paint(FACES[feeling].strip(), CYAN)
    return f"{face}  {pet['name']}" + (f"  ·  {format_limit(limit)}" if limit else "")


def render(pet, feeling, event=None, tokens=0, limit=None):
    """Draw the pet. `event` is what just happened (see pet.feed), which picks the line."""
    level = "egg" if pet["level"] == 0 else f"lvl {pet['level']}"
    stats = [
        f"{pet['name']}  {paint('(' + level + ')', DIM)}",
        f"{paint(bar(pet['hunger'], '♥', '♡'), RED)}  hunger",
        f"{paint(bar(pet['mood'], '★', '☆'), YELLOW)}  mood",
        f"🔥 {pet['streak']}-day streak",
    ]
    if tokens:
        stats.append(f"🤖 {format_tokens(tokens)} tokens today")
    if limit:
        stats.append(f"⏳ {format_limit(limit)}")
    rows = form_for(pet["level"])
    face_row = next(i for i, row in enumerate(rows) if FACE_SLOT in row)

    output = []
    for i in range(max(len(rows), face_row + len(stats))):
        row = rows[i] if i < len(rows) else ""
        art = paint(row.ljust(STATS_COLUMN), CYAN).replace(FACE_SLOT, FACES[feeling])
        stat = stats[i - face_row] if face_row <= i < face_row + len(stats) else ""
        output.append((art + stat).rstrip())

    return "\n".join(output + ["", f'   "{reaction(pet, event or feeling)}"'])


def render_short(pet, feeling, event):
    """One line for the hook, so a commit's output stays readable."""
    face = paint(FACES[feeling].strip(), CYAN)
    return f'{face}  {pet["name"]}: "{reaction(pet, event)}"'
