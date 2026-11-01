import argparse
import json
import sys
import time
from pathlib import Path

from tamagotchi import agent, art, claude, hooks, pet as pet_logic, social, storage

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
    commands.add_parser("watch", help="keep your pet on screen, animated and live (ctrl-c to quit)")
    commands.add_parser("install-agent", help="let your pet react to Claude Code")
    commands.add_parser("uninstall-agent", help="stop reacting to Claude Code")
    commands.add_parser("agent-event", help="used by the Claude Code hooks")
    commands.add_parser("face", help="print just the face, for your shell prompt")
    share = commands.add_parser("share", help="publish your pet to your GitHub profile repo")
    share.add_argument("--push", action="store_true", help="also commit and push it")
    commands.add_parser("profile-update", help="used by the daily GitHub Action")
    friends = commands.add_parser("friends", help="show the leaderboard, or add and remove friends")
    friends.add_argument("action", nargs="?", choices=["add", "remove"])
    friends.add_argument("username", nargs="?")
    return parser.parse_args(argv)


def quick_feeling(pet, now):
    """The feeling without Claude's token count, which is too slow for prompts and status lines."""
    limit = claude.weekly_limit(now)
    status = agent.status(now)
    return pet_logic.feeling(pet, now, 0, limit[0] if limit else 0, status["state"] if status else None)


def face():
    # This runs on every prompt, so failing means an empty string and never an error message.
    try:
        now = time.time()
        print(art.FACES[quick_feeling(load_pet(now), now)].strip())
    except Exception:
        pass
    return 0


def friends(action, username):
    if action == "add":
        return manage_hook(lambda: social.add_friend(username))
    if action == "remove":
        return manage_hook(lambda: social.remove_friend(username))
    now = time.time()
    print(social.leaderboard(load_pet(now), now))
    return 0


def current_mood(pet, now):
    """Return the pet's feeling, plus the extra rows to draw with it."""
    tokens = claude.tokens_today(now)
    limit = claude.weekly_limit(now)
    status = agent.status(now)
    feeling = pet_logic.feeling(pet, now, tokens, limit[0] if limit else 0, status["state"] if status else None)
    return feeling, {"tokens": tokens, "limit": limit, "agent": status}


def agent_event():
    # Runs inside Claude Code, and printing here could feed text into your conversation. So: silence.
    try:
        agent.handle(json.load(sys.stdin), time.time())
    except Exception:
        pass
    return 0


def watch():
    now = time.time()
    if not art.can_animate():
        pet = load_pet(now)
        feeling, extras = current_mood(pet, now)
        print(art.render(pet, feeling, **extras))
        return 0

    # The alternate screen is a blank canvas, and leaving it restores your terminal as it was.
    sys.stdout.write("\033[?1049h\033[?25l")
    try:
        frame = 0
        shown = None
        while True:
            # Reading logs is slower than a frame, so refresh the data every couple of seconds.
            if frame % 5 == 0:
                now = time.time()
                pet = load_pet(now)
                feeling, extras = current_mood(pet, now)
                if feeling != shown or frame % 100 == 0:
                    shown, line = feeling, art.reaction(pet, feeling)
            output = art.render(pet, feeling, frame=frame, line=line, **extras)
            sys.stdout.write(f"\033[H\033[J\n{output}\n\n   ctrl-c to quit\n")
            sys.stdout.flush()
            frame += 1
            time.sleep(0.4)
    except KeyboardInterrupt:
        return 0
    finally:
        sys.stdout.write("\033[?25h\033[?1049l")
        sys.stdout.flush()


def statusline():
    # Claude Code runs this constantly, so stay quiet on failure and never touch the pet's save.
    try:
        now = time.time()
        claude.save_limit(json.load(sys.stdin))
        pet = load_pet(now)
        print(art.render_statusline(pet, quick_feeling(pet, now), claude.weekly_limit(now)))
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
    if args.command == "agent-event":
        return agent_event()
    if args.command == "install-agent":
        return manage_hook(lambda: agent.install(sys.executable))
    if args.command == "uninstall-agent":
        return manage_hook(agent.uninstall)
    if args.command == "watch":
        return watch()
    if args.command == "face":
        return face()
    if args.command == "friends":
        return friends(args.action, args.username)
    if args.command == "profile-update":
        return manage_hook(lambda: social.profile_update(Path.cwd(), time.time()))
    if args.command == "share":
        return manage_hook(lambda: social.share(load_pet(time.time()), time.time(), args.push))

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
    feeling, extras = current_mood(pet, now)
    if args.command is None and art.can_animate():
        line = art.reaction(pet, feeling)
        try:
            art.play(lambda frame: art.render(pet, feeling, frame=frame, line=line, **extras))
        except KeyboardInterrupt:
            pass
    else:
        print(art.render(pet, feeling, event, **extras))
    return 0


# The git hook runs this file directly, so it doesn't depend on `pet` being on PATH.
if __name__ == "__main__":
    sys.exit(main())
