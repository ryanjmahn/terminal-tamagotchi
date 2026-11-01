import os
import re
import shlex
import stat
import subprocess
from pathlib import Path

START = "# >>> terminal-tamagotchi >>>"
END = "# <<< terminal-tamagotchi <<<"
BLOCK = re.compile(re.escape(START) + r"\n.*?" + re.escape(END) + r"\n", re.DOTALL)
SHELL_SHEBANG = re.compile(r"\b(ba|z|k|da)?sh\b")


class HookError(Exception):
    pass


def git(*args):
    result = subprocess.run(["git", *args], capture_output=True, encoding="utf-8", errors="replace", check=True)
    return result.stdout


def hook_path():
    try:
        # Asking git, instead of assuming .git/hooks, also handles subfolders and worktrees.
        return Path(git("rev-parse", "--git-path", "hooks").strip()) / "post-commit"
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise HookError("this isn't a git repository (run `git init` first?)")


def last_commit_lines():
    """Lines added plus removed in HEAD. `git show` also works on the very first commit."""
    total = 0
    for line in git("show", "--numstat", "--format=", "HEAD").splitlines():
        added, deleted, _ = line.split("\t", 2)
        # Binary files report "-" instead of a count.
        total += sum(int(n) for n in (added, deleted) if n.isdigit())
    return total


def read_hook(path):
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise HookError(f"{path} isn't a text file, so I won't touch it. Nothing changed.")


def write_hook(path, text):
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o755
    # Write then swap, so a crash mid-write can't damage an existing hook.
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.chmod(mode)
    os.replace(tmp, path)


def install(python):
    """Add the hook to the current repo. `python` is the interpreter the hook should run."""
    path = hook_path()
    # An absolute path, because hooks may not run with your shell's PATH.
    # `|| true` so a failure here can't stop anything else in the hook.
    block = (
        f"{START}\n"
        "# Feeds your pet on every commit. Remove with `pet uninstall`.\n"
        f"{shlex.quote(python)} -m tamagotchi.cli feed --commit || true\n"
        f"{END}\n"
    )

    if path.is_symlink():
        raise HookError(f"{path} is a symlink, so I won't touch it. Nothing changed.")
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        write_hook(path, "#!/bin/sh\n" + block)
        return f"Installed! Your next commit in this repo feeds your pet.\n  hook: {path}"

    text = read_hook(path)
    if BLOCK.search(text):
        write_hook(path, BLOCK.sub(lambda _: block, text))
        return f"Already installed, so I just refreshed it.\n  hook: {path}"

    if not os.access(path, os.X_OK):
        # Git ignores non-executable hooks, and making it executable would re-enable the old code.
        raise HookError(f"{path} exists but is disabled (not executable). Nothing changed.")
    first, _, rest = text.partition("\n")
    if first.startswith("#!"):
        if not SHELL_SHEBANG.search(first):
            raise HookError(f"{path} isn't a shell script ({first}), so I can't add to it. Nothing changed.")
        new_text = f"{first}\n{block}{rest}"
    else:
        new_text = block + text
    write_hook(path, new_text)
    return (
        "You already had a post-commit hook, so I kept it and added the pet to it.\n"
        "The pet runs first, in case your hook ends early with something like `exit 0`.\n"
        f"  hook: {path}"
    )


def uninstall():
    path = hook_path()
    text = read_hook(path) if path.exists() else ""
    if not BLOCK.search(text):
        return "The hook isn't installed in this repo, so there's nothing to remove."

    remaining = BLOCK.sub("", text)
    body = remaining.partition("\n")[2] if remaining.startswith("#!") else remaining
    if body.strip():
        write_hook(path, remaining)
        return f"Removed the pet from your hook and left the rest as it was.\n  hook: {path}"
    path.unlink()
    return "Hook removed. Commits in this repo won't feed your pet anymore."
