import math
import os
import random
import sys

COLOR = sys.stdout.isatty() and "NO_COLOR" not in os.environ and os.environ.get("TERM") != "dumb"
RED, YELLOW, CYAN, DIM = "31", "33", "36", "2"

# Each face fills the box's 9 cells. ﹏ is double-width, so its faces get one less space.
FACES = {
    "happy": "  ◕ ‿ ◕  ",
    "content": "  • ‿ •  ",
    "hungry": "  • ﹏ • ",
    "sad": "  ╥ ﹏ ╥ ",
    "sleepy": "  - . -  ",
}

LINES = {
    "happy": ["life is good", "best. human. ever.", "*happy wiggle*"],
    "content": ["just vibing", "ship anything good today?", "*blinks at you*"],
    "hungry": ["...did you forget about me?", "a small commit would be nice", "*stomach rumbles*"],
    "sad": ["i have known only hunger", "remember when you used to commit?", "tell my story"],
    "sleepy": ["go to sleep bro 😴", "zzz... merge conflict... zzz", "it's so late, close the laptop"],
}


def paint(text, code):
    return f"\033[{code}m{text}\033[0m" if COLOR else text


def bar(value, full, empty):
    # Round up, so the last heart only disappears when the stat really hits 0.
    filled = math.ceil(value)
    return full * filled + empty * (5 - filled)


def render(pet, feeling):
    border = lambda text: paint(text, CYAN)
    return "\n".join([
        border("   ╭─────────╮"),
        f"{border('   │')}{FACES[feeling]}{border('│')}   {pet['name']}  {paint('(lvl ' + str(pet['level']) + ')', DIM)}",
        f"{border('   ╰─┬─────┬─╯')}   {paint(bar(pet['hunger'], '♥', '♡'), RED)}  hunger",
        f"{border('     ┘     └')}     {paint(bar(pet['mood'], '★', '☆'), YELLOW)}  mood",
        f"                 🔥 {pet['streak']}-day streak",
        "",
        f'   "{random.choice(LINES[feeling])}"',
    ])
