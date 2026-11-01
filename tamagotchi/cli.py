import argparse
import json
import sys
import time

from tamagotchi import art, claude, hooks, pet as pet_logic, storage

MAX_NAME_LENGTH = 20


def load_pet(now):
    # Merging over new_pet fills in any field an older save file doesn't have.
    pet = {**pet_logic.new_pet(now), **(storage.load() or {})}
    pet_logic.decay(pet, now)
    return pet


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="pet", description="An ASCII pet that feeds on your git commits.")
    commands = parser.add_subparsers(dest="command")
    feed = commands.add_parser("feed", help="give your pet a snack")
    feed.add_argument("--lines", type=int, default=0, help="lines changed, bigger snacks give a little more")
    feed.add_argument("--commit", action="store_true", help="feed from the latest commit (used by the git hook)")
    name = commands.add_parser("name", help="rename your pet")
    name.add_argument("name")
    commands.add_parser("install", help="feed your pet on every commit in this repo")
    commands.add_parser("uninstall", help="remove the hook from this repo")
    commands.add_parser("reset", help="start over with a new egg")
    commands.add_parser("statusline", help="status line for Claude Code, which also tracks your weekly limit")
    return parser.parse_args(argv)


def statusline():
    # Claude Code runs this constantly, so stay quiet on failure and never touch the pet's save.
    try:
        now = time.time()
        claude.save_limit(json.load(sys.stdin))
        limit = claude.weekly_limit(now)
        pet = load_pet(now)
        feeling = pet_logic.feeling(pet, now, limit_used=limit[0] if limit else 0)
        print(art.render_statusline(pet, feeling, limit))
    except Exception:
        pass
    return 0


def feed_from_commit():
    # Runs inside every commit, so any failure is a small warning and nothing more.
    # shortcut: amends, rebases and cherry-picks also feed, check `git reflog -1` if that gets abused.
    try:
        now = time.time()
        pet = load_pet(now)
        event = pet_logic.feed(pet, now, hooks.last_commit_lines())
        storage.save(pet)
        print(art.render_short(pet, pet_logic.feeling(pet, now), event))
    except Exception as error:
        print(f"pet: couldn't feed your pet ({error}), but your commit is fine", file=sys.stderr)
    return 0


def manage_hook(action):
    try:
        print(action())
    except (hooks.HookError, OSError) as error:
        print(f"pet: {error}", file=sys.stderr)
        return 1
    return 0


def confirm(question):
    try:
        return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


def main(argv=None):
    args = parse_args(argv)
    if args.command == "feed" and args.commit:
        return feed_from_commit()
    if args.command == "install":
        return manage_hook(lambda: hooks.install(sys.executable))
    if args.command == "uninstall":
        return manage_hook(hooks.uninstall)
    if args.command == "statusline":
        return statusline()

    now = time.time()
    pet = load_pet(now)
    event = None

    if args.command == "feed":
        event = pet_logic.feed(pet, now, args.lines)
    elif args.command == "name":
        name = args.name.strip()
        if not name or len(name) > MAX_NAME_LENGTH or not name.isprintable():
            print(f"pet: names must be 1-{MAX_NAME_LENGTH} printable characters", file=sys.stderr)
            return 1
        pet["name"] = name
    elif args.command == "reset":
        if not confirm(f"Say goodbye to {pet['name']} and start over with a new egg?"):
            print(f"Phew. {pet['name']} stays.")
            return 0
        pet = pet_logic.new_pet(now)

    storage.save(pet)
    tokens = claude.tokens_today(now)
    limit = claude.weekly_limit(now)
    limit_used = limit[0] if limit else 0
    print(art.render(pet, pet_logic.feeling(pet, now, tokens, limit_used), event, tokens, limit))
    return 0


# The git hook runs this file directly, so it doesn't depend on `pet` being on PATH.
if __name__ == "__main__":
    sys.exit(main())
