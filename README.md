# Terminal Tamagotchi 🐣

```
   ╭─────────╮
   │  ◕ ‿ ◕  │   Porky  (lvl 4)
   ╰─┬─────┬─╯   ♥♥♥♥♡  hunger
     ┘     └     ★★★★☆  mood
                 🔥 6-day streak

   "nom nom 🍪"
```

A little ASCII pet that lives in your terminal and feeds on your git commits. Commit and it thrives. Stop committing and it will look at you like this: `╥ ﹏ ╥`

Python 3 standard library only, so there's nothing else to install.

## Install

```sh
git clone https://github.com/ryanjmahn/terminal-tamagotchi.git
cd terminal-tamagotchi
python3 -m pip install -e .
pet
```

If pip says `externally-managed-environment`, or complains that `setup.py` wasn't found (the older pip that ships with macOS does this), install into a virtual environment instead:

```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -e .
```

The `pet` command only works while that environment is active, so run `source .venv/bin/activate` again in new terminals. Installed hooks keep working either way.

Then go to any repo you want to feed your pet from, and install the hook:

```sh
cd ~/code/some-project
pet install
```

Your next commit there feeds your pet. You get one pet, shared across every repo.

## Commands

| Command | What it does |
|---|---|
| `pet` | Show your pet, its stats, and what it's feeling |
| `pet feed` | Give it a snack by hand (no judgment) |
| `pet name <name>` | Rename it (the default is Porky) |
| `pet install` | Feed your pet on every commit in the current repo |
| `pet uninstall` | Remove the hook from the current repo |
| `pet reset` | Start over with a new egg (it asks first) |

## How feeding works

Every commit is a snack:

| | Small commit | 200+ lines changed |
|---|---|---|
| Hunger | +1 heart | +1.5 hearts |
| XP | +10 | +20 |
| Mood | +0.5 stars | +0.5 stars |

Rewards stop growing at 200 lines, so a 2000-line commit is a very expensive way to earn nothing extra.

**Streaks** count consecutive calendar days with at least one commit. Extending your streak adds another half star of mood. Miss a whole day and it goes back to zero.

**Time passes even when you're away.** There's no background process. Each time your pet wakes up, it works out what it lost since last time:

- Hunger drops 1.5 hearts a day, so it's noticeably hungry after a day and very hungry after three.
- Mood drops 1 star a day.
- Eggs don't get hungry. They're eggs.

**Evolution:** your pet hatches on its first commit, then changes form as it levels up.

```
      ╭─────╮
     ╱  · ·  ╲
    │  · · ·  │  egg
     ╲       ╱
      ╰─────╯

   ╭─────────╮
   │  • ‿ •  │   lvl 1: hatchling (your first commit)
   ╰─┬─────┬─╯
     ┘     └

    /\     /\
   ╭─────────╮
   │  • ‿ •  │   lvl 5: 500 XP, about 40 commits
  /╰─┬─────┬─╯\
     ┘     └

      ▲ ▲ ▲
   ╔══╧═╧═╧══╗
   ║  • ‿ •  ║   lvl 10: 2250 XP, about 170 commits
  /╚═╤═════╤═╝\
     ┘     └
```

**Moods:**

| Face | Mood | When |
|---|---|---|
| `★ ▽ ★` | Ecstatic | For an hour after hatching or leveling up |
| `- . -` | Sleepy | 1am to 5am. It will tell you to go to bed. |
| `╥ ﹏ ╥` | Sad | Nearly out of hunger or mood |
| `• ﹏ •` | Hungry | About a day since its last snack |
| `x _ x` | Dead (for now) | Weekly Claude limit used up, until it resets |
| `◉ ﹏ ◉` | Nervous | 80%+ of your weekly Claude limit used |
| `◉ ‿ ◉` | Wired | 250k+ Claude Code tokens today |
| `◕ ‿ ◕` | Happy | Well fed and in a good mood |
| `• ‿ •` | Content | Everything else |

## Claude Code usage

If you use [Claude Code](https://claude.com/product/claude-code), your pet notices. There's nothing to set up:

```
   ╭─────────╮
   │  ◉ ‿ ◉  │   Porky  (lvl 4)
   ╰─┬─────┬─╯   ♥♥♥♥♡  hunger
     ┘     └     ★★★★☆  mood
                 🔥 6-day streak
                 🤖 412k tokens today

   "did you and claude even sleep?"
```

Tokens never feed your pet. Commits are still the only food, so it can't level up from you burning tokens. They only change what it shows and says.

The count is today's input and output tokens from the logs in `~/.claude/projects`, leaving out cached tokens. Those logs hold your full conversations, but your pet only uses each message's id, timestamp and token counts, and it doesn't save or send any of it. The log format isn't an official interface, so if it ever changes, the line just disappears.

### Weekly limit

On a Claude subscription, your pet can also watch your weekly limit. It gets nervous at 80% and drops dead at 100%, then comes back when the limit resets, with its level and stats untouched.

Claude Code only shares this percentage with status line commands, so add this to `~/.claude/settings.json`:

```json
{
  "statusLine": {
    "type": "command",
    "command": "pet statusline"
  }
}
```

Your pet then appears in Claude Code's status line, and `pet` shows the last percentage it saw. That number only updates while Claude Code is running. If you already have a status line, adding this replaces it.

## Good to know

- **It can't block your commits.** The hook runs after the commit already exists. If anything goes wrong, you get at most a one-line warning.
- **It's safe with your existing hooks.** If you already have a shell `post-commit` hook, your pet is added alongside it, and `pet uninstall` puts it back exactly as it was. If it can't edit your hook safely, it leaves it alone and tells you.
- **Hooks are per repo and don't get pushed.** Anyone who clones a repo, including you on another laptop, has to run `pet install` there.
- **Amends, rebases and cherry-picks count as commits too.** Yes, you can cheat. Your pet won't know. You will.
- **Your save file** is `~/.terminal-tamagotchi/pet.json`.

## Development

```sh
python3 -m unittest discover tests
```

The hook tests run real git in a temporary repo with a temporary home folder, so they won't touch your pet.

## Roadmap

Ideas for later:

- **Sick when CI fails:** a GitHub Action or check that marks the pet sick when builds or tests are red
- **Coding agent mode:** watch Claude Code (or another agent) and react: cheer when it finishes a task, get nervous in long loops, ping you when it's waiting for approval
- **Bad-habit reactions:** look scared after a force-push to main
- **GitHub profile pet:** show it in your profile README with a GitHub Action that updates it daily
- **Friends:** compare pets with friends, leaderboards
- **Shell prompt integration:** a tiny pet face in your terminal prompt
