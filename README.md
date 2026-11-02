<div align="center">

# Terminal Tamagotchi 🐣

An ASCII pet that lives in your terminal and feeds on your git commits.

[![Stars](https://img.shields.io/github/stars/ryanjmahn/terminal-tamagotchi?style=flat&color=black)](https://github.com/ryanjmahn/terminal-tamagotchi/stargazers)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-black.svg)](https://www.python.org)
[![Dependencies: none](https://img.shields.io/badge/Dependencies-none-black.svg)](pyproject.toml)

</div>

```
   ╭─────────╮
   │  ◕ ‿ ◕  │   Porky  (lvl 4)
   ╰─┬─────┬─╯   ♥♥♥♥♡  hunger
     ┘     └     ★★★★☆  mood
                 🔥 6-day streak

   "nom nom 🍪"
```

Commit and your pet thrives. Stop committing and it will look at you like this: `╥ ﹏ ╥`. That is the whole idea. Terminal Tamagotchi hooks into your git repos, turns every commit into a snack, and works out how hungry your pet got while you were away.

It is written with the Python 3 standard library only, so there's nothing else to install. You get one pet, shared across every repo.

> **It can't block your commits.** The hook runs after the commit already exists. If anything goes wrong, you get at most a one-line warning.

## Why this exists

A streak counter is easy to ignore. A small face that gets sadder the longer you stay away is harder. Terminal Tamagotchi puts that face where you already work, with no account to create and no background process to keep running.

## Features

- Commit feeding. Every commit in a repo with the hook installed gives your pet hunger, XP, and mood.
- Streaks. Consecutive days with a commit keep the streak alive and lift your pet's mood.
- Evolution. Your pet hatches on its first commit, then changes form as it levels up.
- Moods. Twelve faces react to hunger, the time of day, and what Claude Code is doing.
- Animations. Your pet blinks, sweats, snores, and wiggles. `pet watch` keeps it on screen, live.
- [Claude Code usage](#claude-code-usage). See today's token count, and watch your pet panic as your weekly limit runs out.
- [Coding agent mode](#coding-agent-mode). Your pet follows a Claude Code session and tells you when Claude needs your approval.
- [Shell prompt](#shell-prompt). Keep a tiny pet in your prompt.
- [GitHub profile pet](#github-profile-pet). Show your pet on your profile, where it can starve in public.
- [Friends leaderboard](#friends). Rank your pet against your friends' by XP, with no server involved.

## How it works

1. `pet install` adds a `post-commit` hook to the current repo.
2. You commit, and the hook feeds your pet based on the size of the commit.
3. Your pet's state is saved to `~/.terminal-tamagotchi/pet.json`.
4. The next time your pet wakes up, it works out what it lost since last time.

There's no background process. Hunger and mood are worked out from the time that has passed, so your pet is always up to date when you look at it.

## Quick start

```sh
git clone https://github.com/ryanjmahn/terminal-tamagotchi.git
cd terminal-tamagotchi
python3 -m pip install -e .
pet
```

Then go to any repo you want to feed your pet from, and install the hook:

```sh
cd ~/code/some-project
pet install
```

Your next commit there feeds your pet.

**Pip says `externally-managed-environment`, or that `setup.py` wasn't found?** The older pip that ships with macOS does the second one. Install into a virtual environment instead:

```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -e .
```

The `pet` command only works while that environment is active, so run `source .venv/bin/activate` again in new terminals. Installed hooks keep working either way.

## Commands

| Command | What it does |
|---|---|
| `pet` | Show your pet, its stats, and what it's feeling |
| `pet feed` | Give it a snack by hand (no judgment) |
| `pet name <name>` | Rename it (the default is Porky) |
| `pet watch` | Keep your pet on screen, animated and live (ctrl-c to quit) |
| `pet face` | Print just the face, for your shell prompt |
| `pet share` | Publish your pet to your GitHub profile repo (`--push` to commit and push too) |
| `pet friends` | Show the leaderboard |
| `pet friends add <user>` | Add a friend by GitHub username (`remove` takes them off) |
| `pet install` | Feed your pet on every commit in the current repo |
| `pet uninstall` | Remove the hook from the current repo |
| `pet install-agent` | Let your pet react to Claude Code |
| `pet uninstall-agent` | Stop reacting to Claude Code |
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

**Time passes even when you're away:**

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
| `◕ o ◕` | Calling you | Claude Code is waiting for your approval |
| `◉ ﹏ ◉` | Nervous | 80%+ of your weekly Claude limit used |
| `@ ﹏ @` | Worried | Claude Code has been going for 75+ tool calls or 20+ minutes |
| `^ ▽ ^` | Cheering | Claude Code just finished |
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

### Coding agent mode

Your pet can watch Claude Code work:

```sh
pet install-agent
```

Restart Claude Code, then run `pet watch` in a terminal off to the side. Your pet shows what Claude is up to, cheers when it finishes, and starts worrying during very long runs. On macOS you also get a notification when Claude needs your approval, and when a run of 5+ minutes finishes.

```
   ╭─────────╮
   │  ◕ o ◕  │   Porky  (lvl 4)
   ╰─┬─────┬─╯   ♥♥♥♥♡  hunger
     ┘     └     ★★★★☆  mood
                 🔥 6-day streak
                 👀 claude needs your approval!

   "CLAUDE NEEDS YOU"
```

This adds hooks to `~/.claude/settings.json` and leaves the rest of the file alone, and `pet uninstall-agent` takes them back out. The hooks receive your prompts and tool output, but your pet only uses the event name, session id and notification type, and it doesn't save or send any of it. It follows one session at a time, so with several open, the most recently active one wins.

## Animations

`pet` plays a quick animation when you run it in a terminal, and `pet watch` keeps it going: your pet blinks, sweats, snores and wiggles depending on its mood. Piped output and terminals under 70 columns just get the still picture.

## Shell prompt

Keep a tiny pet in your prompt. For zsh, add this to `~/.zshrc`:

```sh
setopt PROMPT_SUBST
PROMPT='$(pet face 2>/dev/null) '"$PROMPT"
```

For bash, add this to `~/.bashrc`:

```sh
PS1='$(pet face 2>/dev/null) '"$PS1"
```

## GitHub profile pet

Show your pet on your GitHub profile, and watch it get hungry if you stop sharing.

1. Create a public repo named exactly after your username (like `github.com/you/you`) and clone it. GitHub shows that repo's README on your profile.
2. Run `pet share` inside the clone, then commit and push what it created.

That adds three files: your pet's snapshot (`pet.json`), a section in your README (between markers, so the rest of your README stays yours), and a GitHub Action that redraws your pet every day. To push a file in `.github/workflows`, a fine-grained token needs the **Workflows** permission as well as **Contents**.

The Action runs on GitHub, so it can't see your laptop. It applies the hunger your pet has lost since your last share, and only `pet share --push` brings it back up. Share often, or it will starve in public.

The snapshot is public and holds only your pet's name, XP, hunger, mood, streak, last fed date and last update time.

## Friends

Anyone who has run `pet share` can be on your leaderboard:

```
$ pet friends add octocat
$ pet friends
  1.   ◕ ‿ ◕   Porky (you)                        lvl 4     320 xp  ♥♥♥♥♡  🔥 6
  2.   • ﹏ •  Mochi (@octocat)                   lvl 2      80 xp  ♥♥♡♡♡  🔥 0
```

Rankings go by XP, and hunger is worked out from when each pet was last shared. There's no server: your pet just reads each friend's public `pet.json`. That also means scores are self-reported, so this runs on the honor system.

## Good to know

- **It's safe with your existing hooks.** If you already have a shell `post-commit` hook, your pet is added alongside it, and `pet uninstall` puts it back exactly as it was. If it can't edit your hook safely, it leaves it alone and tells you.
- **Hooks are per repo and don't get pushed.** Anyone who clones a repo, including you on another laptop, has to run `pet install` there.
- **Amends, rebases and cherry-picks count as commits too.** Yes, you can cheat. Your pet won't know. You will.
- **Your save file** is `~/.terminal-tamagotchi/pet.json`.

## Tech stack

- Python 3.8+ and its standard library, with no third-party dependencies
- Git `post-commit` hooks for feeding
- Claude Code hooks and status line for the agent features
- GitHub Actions and public `pet.json` files for the profile pet and leaderboard
- A local JSON file for your save

## Contributing

Issues and pull requests are welcome. To run the tests:

```sh
python3 -m unittest discover tests
```

The hook tests run real git in a temporary repo with a temporary home folder, so they won't touch your pet.

## Roadmap

Ideas for later:

- **Sick when CI fails:** a GitHub Action or check that marks the pet sick when builds or tests are red
- **More agents:** coding agent mode for agents other than Claude Code
- **Bad-habit reactions:** look scared after a force-push to main

## Credits

Built and maintained by [@ryanjmahn](https://github.com/ryanjmahn).

## Star the repo

If your pet makes you commit a little more often, star the repo. It is the simplest way to help the next person find it.
