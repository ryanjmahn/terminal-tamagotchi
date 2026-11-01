import json
import math
import re
import subprocess
from datetime import date
from pathlib import Path

from tamagotchi import art, hooks, pet as pet_logic, storage

FRIENDS_PATH = Path.home() / ".terminal-tamagotchi" / "friends.json"
SNAPSHOT_NAME = "pet.json"
WORKFLOW_PATH = ".github/workflows/pet.yml"
SNAPSHOT_URL = "https://raw.githubusercontent.com/{user}/{user}/HEAD/" + SNAPSHOT_NAME
USERNAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}")
SYSTEM_CERTIFICATES = "/etc/ssl/cert.pem"
MAX_SNAPSHOT_BYTES = 64 * 1024
MAX_XP = 10 ** 9
MAX_STREAK = 10 ** 6
START = "<!-- terminal-tamagotchi:start -->"
END = "<!-- terminal-tamagotchi:end -->"
PROJECT_URL = "https://github.com/ryanjmahn/terminal-tamagotchi"

WORKFLOW = f"""\
name: Update pet
on:
  schedule:
    - cron: "17 6 * * *"
  workflow_dispatch:
permissions:
  contents: write
jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: "3.12"
      - run: pip install git+{PROJECT_URL}.git
      - run: pet profile-update
      - run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add README.md
          git diff --cached --quiet || git commit -m "Update pet"
          git push
"""


def snapshot(pet):
    """The only pet data that ever gets published."""
    return {key: pet[key] for key in ("name", "xp", "hunger", "mood", "streak", "last_fed", "last_update")}


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"not a number: {value!r}")
    return value


def whole_number(value, largest):
    if number(value) != int(value) or not 0 <= value <= largest:
        raise ValueError(f"out of range: {value!r}")
    return int(value)


def from_snapshot(data):
    """Build a pet from a snapshot, which may be anyone's. Raises if anything looks wrong."""
    name = data["name"]
    # isprintable rejects escape codes, which could otherwise control your terminal.
    if not isinstance(name, str) or not 1 <= len(name) <= 20 or not name.isprintable():
        raise ValueError("bad name")
    last_fed = data["last_fed"]
    if last_fed is not None:
        date.fromisoformat(last_fed)
    xp = whole_number(data["xp"], MAX_XP)
    return {
        **pet_logic.new_pet(number(data["last_update"])),
        "name": name,
        "xp": xp,
        # Worked out from XP instead of trusted, so the numbers on a leaderboard can't disagree.
        "level": pet_logic.level_for(xp),
        "hunger": min(pet_logic.MAX_STAT, max(0, number(data["hunger"]))),
        "mood": min(pet_logic.MAX_STAT, max(0, number(data["mood"]))),
        "streak": whole_number(data["streak"], MAX_STREAK),
        "last_fed": last_fed,
    }


def update_readme(folder, pet, now):
    """Draw the pet into the README between its markers, leaving the rest of the file alone."""
    picture = art.render(pet, pet_logic.feeling(pet, now))
    picture = re.sub(r"\033\[[0-9;]*m", "", picture)
    block = f"{START}\n```\n{picture}\n```\n\n<sub>Fed by [terminal-tamagotchi]({PROJECT_URL})</sub>\n{END}"
    path = folder / "README.md"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.DOTALL)
    if pattern.search(text):
        text = pattern.sub(lambda _: block, text)
    else:
        text = f"{text.rstrip()}\n\n{block}\n".lstrip()
    path.write_text(text, encoding="utf-8")


def profile_update(folder, now):
    """What the daily Action runs: redraw the README with the time since the last share applied."""
    try:
        data = json.loads((folder / SNAPSHOT_NAME).read_text(encoding="utf-8"))
        pet = from_snapshot(data)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise hooks.HookError(f"couldn't read {SNAPSHOT_NAME} here: {error}")
    pet_logic.decay(pet, now)
    update_readme(folder, pet, now)
    return f"Updated README.md for {pet['name']}."


def profile_repo():
    """Return the top folder of the profile repo we're in, refusing any other repo."""
    message = (
        "run this inside your GitHub profile repo, the one named after your username "
        "(like github.com/you/you). Nothing changed."
    )
    try:
        top = hooks.git("rev-parse", "--show-toplevel").strip()
        origin = hooks.git("remote", "get-url", "origin").strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise hooks.HookError(message)
    # This publishes files, so make sure it can't land in some other project by accident.
    match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$", origin)
    if not match or match.group(1).lower() != match.group(2).lower():
        raise hooks.HookError(message)
    return Path(top)


def share(pet, now, push=False):
    folder = profile_repo()
    storage.write_json(folder / SNAPSHOT_NAME, snapshot(pet))
    workflow = folder / WORKFLOW_PATH
    workflow.parent.mkdir(parents=True, exist_ok=True)
    workflow.write_text(WORKFLOW, encoding="utf-8")
    update_readme(folder, pet, now)

    paths = [SNAPSHOT_NAME, WORKFLOW_PATH, "README.md"]
    if not push:
        return (
            f"{pet['name']} is ready to share. To publish:\n"
            f"  git add {' '.join(paths)}\n"
            f'  git commit -m "Update {pet["name"]}"\n'
            "  git push\n"
            "Next time, `pet share --push` does all of that for you."
        )
    try:
        repo = ["-C", str(folder)]
        hooks.git(*repo, "add", *paths)
        if not hooks.git(*repo, "status", "--porcelain", "--", *paths).strip():
            return "Nothing new to share."
        hooks.git(*repo, "commit", "-m", f"Update {pet['name']}")
        hooks.git(*repo, "push")
    except subprocess.CalledProcessError as error:
        raise hooks.HookError(f"git failed: {error.stderr.strip()}")
    return f"Shared {pet['name']}! Your profile shows it now."


def read_friends():
    try:
        friends = json.loads(FRIENDS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(friends, list):
        return []
    return [f for f in friends if isinstance(f, str) and USERNAME.fullmatch(f)]


def add_friend(username):
    if not username or not USERNAME.fullmatch(username):
        raise hooks.HookError("usage: pet friends add <github-username>")
    friends = read_friends()
    if username.lower() in (f.lower() for f in friends):
        return f"@{username} is already on your list."
    storage.write_json(FRIENDS_PATH, friends + [username])
    return f"Added @{username}. Run `pet friends` to see the leaderboard."


def remove_friend(username):
    if not username:
        raise hooks.HookError("usage: pet friends remove <github-username>")
    friends = read_friends()
    kept = [f for f in friends if f.lower() != username.lower()]
    if len(kept) == len(friends):
        return f"@{username} wasn't on your list."
    storage.write_json(FRIENDS_PATH, kept)
    return f"Removed @{username}."


def tls_context():
    import ssl

    context = ssl.create_default_context()
    # Python from python.org on macOS ships without trusted certificates, so add the system's list.
    if Path(SYSTEM_CERTIFICATES).exists():
        context.load_verify_locations(SYSTEM_CERTIFICATES)
    return context


def fetch_friend(username, now):
    """Return a friend's pet with time applied, or None if there's no usable snapshot."""
    # Imported here because it's slow, and every prompt runs this program when the face is on.
    from urllib.request import urlopen

    try:
        with urlopen(SNAPSHOT_URL.format(user=username), timeout=5, context=tls_context()) as response:
            raw = response.read(MAX_SNAPSHOT_BYTES + 1)
        if len(raw) > MAX_SNAPSHOT_BYTES:
            return None
        pet = from_snapshot(json.loads(raw))
        pet_logic.decay(pet, now)
        return pet
    except Exception:
        # It's someone else's file on the internet, so any failure just means "no pet found".
        return None


def leaderboard(mine, now):
    from concurrent.futures import ThreadPoolExecutor

    friends = read_friends()
    with ThreadPoolExecutor(max_workers=8) as pool:
        pets = list(pool.map(lambda friend: fetch_friend(friend, now), friends))

    entries = [(mine, f"{mine['name']} (you)")]
    missing = []
    for friend, pet in zip(friends, pets):
        if pet:
            entries.append((pet, f"{pet['name']} (@{friend})"))
        else:
            missing.append(friend)

    rows = []
    for rank, (pet, label) in enumerate(sorted(entries, key=lambda e: e[0]["xp"], reverse=True), 1):
        face = art.FACES[pet_logic.feeling(pet, now)]
        hearts = art.bar(pet["hunger"], "♥", "♡")
        rows.append(f"{rank:>3}. {face} {label:<34} lvl {pet['level']:<3} {pet['xp']:>6} xp  {hearts}  🔥 {pet['streak']}")
    rows += [f"  -  @{friend}: no pet found (no `pet share` yet, or are you offline?)" for friend in missing]
    if not friends:
        rows += ["", "   It's lonely up here. Add someone with `pet friends add <github-username>`."]
    return "\n".join(rows)
