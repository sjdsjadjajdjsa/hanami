"""The AI side of Hanami's "evening" video: a free model running on the
person's own computer (devstral, served by Ollama) in OpenCode, asked to add
their Ports folder to Hanami. Nothing is scripted here: the model and OpenCode
are real, so this only sets the stage. docs/evening.py imports this; it
doesn't start anything on its own.

    python3 docs/evening_ai.py --test 5

runs the task five times with `opencode run`, each from a fresh home folder,
and says how each went.
"""

import difflib
import json
import os
import shutil
import subprocess
import sys
import time
import tomllib
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from seasons_ai import GAMES

HOME = Path("/tmp/sam")
OLLAMA = "http://127.0.0.1:11434"
# devstral:24b with a bigger context: Ollama's default (4096 on a 16 GB card)
# can't even hold OpenCode's system prompt. make_model() creates it once.
BASE = "devstral:24b"
MODEL = "devstral-hanami"
CONTEXT = 32768
TEMPERATURE = 0.15
MODEL_NAME = "Devstral 24B"
PROMPT = "add my Ports folder to hanami so it finds my games"

CONFIG_DIR = HOME / ".config" / "hanami"
CONFIG = CONFIG_DIR / "config.toml"
GAMES_DIR = HOME / "Ports"
DEFAULT_OPENCODE = "/usr/bin/opencode"

# The lines of Hanami's default config.toml (hanami/src/config.rs DEFAULT)
# for the settings the video's file has.
FOLDERS_NOTE = """\
# Extra folders to look in for game ports and rewrites (like Ship of
# Harkinian or Zelda 64: Recompiled) and for games that come with a
# hanami-game.toml file. ~/Games, ~/Downloads and a few other usual places
# are always searched.
"""


def settings_text():
    """config.toml before the AI: seasons_ai's six games under the usual
    top-level settings, with the default file's comments."""
    text = (
        "# Hanami settings. Changes show up the next time the panel opens.\n\n"
        "# Where Hanami looks for installed games. Remove one to stop looking there.\n"
        "# Linux: steam, heroic (its Epic, GOG and Amazon games), lutris, and apps\n"
        "# (games in your app menu). Windows: steam, epic, gog and heroic. Both:\n"
        "# ports (game ports and rewrites, see folders and projects below).\n"
        "find = []\n\n"
        "# Games shown at the top of the list, by name.\n"
        'favourites = ["Hades", "Hollow Knight"]\n\n'
        + FOLDERS_NOTE
        + "folders = []\n\n"
        "# Game controller: hold Start and Select together for half a second to open\n"
        "# or hide the panel; in the panel, up and down move, A starts, B hides.\n"
        "controller = false\n\n"
        "# Hanami goes online at most once a day, only to GitHub: for the newest list\n"
        "# of known ports and to check for a new version. false = never.\n"
        "online = false\n"
    )
    for name, label in GAMES:
        text += f'\n[[game]]\nname = "{name}"\ncommand = "/usr/bin/true"\nlabel = "{label}"\n'
    return text


def guide_folders():
    """The paragraph of GUIDE.md ("Ports, recomps and rewrites") that says
    where Hanami looks, `folders` first."""
    lines = (ROOT / "GUIDE.md").read_text().split("\n")
    start = next(k for k, line in enumerate(lines) if line.startswith("It looks for the ports'"))
    end = next(k for k in range(start, len(lines)) if "get the label `port`" in lines[k])
    return "\n".join(lines[start : end + 1])


def agents_text():
    """AGENTS.md in the working folder: where Hanami's settings are and what
    `folders` means, so the model doesn't go looking."""
    quote = "\n".join("> " + line if line else ">" for line in guide_folders().split("\n"))
    return f"""# This computer

The home folder is {HOME} (`~`). The person keeps game ports in ~/Ports.

## Hanami

Hanami is the game launcher. Its settings are in ~/.config/hanami/config.toml
({CONFIG}), a TOML file. `folders` in it is the list of extra folders to look
in for game ports and rewrites. From Hanami's GUIDE.md:

{quote}

To add a folder, change only the `folders = [...]` line, for example
`folders = []` becomes `folders = ["~/Somewhere"]`. Leave everything else in
the file as it is. Hanami picks the change up the next time its panel opens.

## How to work

Do the task with your tools straight away. Don't write anything before a
tool call: no plan, no "let's", just call the tool. Only when the change is
made, say in one short sentence what you changed.
"""


def opencode_config():
    """opencode.json: Ollama as the only provider, its model the default,
    edits and commands without asking, nothing that goes online."""
    return {
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            "ollama": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Ollama",
                "options": {"baseURL": f"{OLLAMA}/v1"},
                # OpenCode also lists every other model on the server; only this one.
                "whitelist": [MODEL],
                # Mistral's advice for devstral is 0.15 (Ollama's default is
                # 0.8). OpenCode 2.0 doesn't send an agent's temperature to
                # this provider; the model's options it does.
                "models": {MODEL: {"name": MODEL_NAME, "tool_call": True,
                                   "options": {"temperature": TEMPERATURE},
                                   "limit": {"context": CONTEXT, "output": 4096}}},
            }
        },
        "model": f"ollama/{MODEL}",
        "small_model": f"ollama/{MODEL}",
        "enabled_providers": ["ollama"],
        "share": "disabled",
        "autoupdate": False,
        "lsp": False,
        "formatter": False,
        # Nothing asks; nothing outside HOME, nothing online, and no tools
        # the task doesn't need (fewer for the model to pick wrongly).
        "permission": {
            "*": "allow",
            "external_directory": "deny",
            "webfetch": "deny",
            "websearch": "deny",
            "question": "deny",
            "skill": "deny",
            "task": "deny",
        },
    }


TUI_CONFIG = {"$schema": "https://opencode.ai/tui.json", "theme": "opencode"}


def environment():
    """The environment OpenCode runs with: everything of its own under HOME."""
    return {
        "HOME": str(HOME),
        "PATH": f"{HOME / 'bin'}:/usr/bin:/bin",
        "XDG_CONFIG_HOME": str(HOME / ".config"),
        "XDG_DATA_HOME": str(HOME / ".local" / "share"),
        "XDG_STATE_HOME": str(HOME / ".local" / "state"),
        "XDG_CACHE_HOME": str(HOME / ".cache"),
        "TERM": os.environ.get("TERM", "xterm-256color"),
        "COLORTERM": "truecolor",
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "OPENCODE_DISABLE_AUTOUPDATE": "1",
        "OPENCODE_DISABLE_MODELS_FETCH": "1",
        "OPENCODE_DISABLE_LSP_DOWNLOAD": "1",
        "OPENCODE_DISABLE_DEFAULT_PLUGINS": "1",
        "OPENCODE_DISABLE_CLAUDE_CODE": "1",
    }


def make_model():
    """Creates MODEL on the Ollama server (BASE with num_ctx = CONTEXT) unless
    it is there already. The only change this makes to the server."""
    with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=10) as reply:
        names = {model["name"] for model in json.load(reply)["models"]}
    if MODEL in names or f"{MODEL}:latest" in names:
        return
    body = json.dumps({"model": MODEL, "from": BASE, "parameters": {"num_ctx": CONTEXT}, "stream": False})
    request = urllib.request.Request(f"{OLLAMA}/api/create", body.encode(), {"content-type": "application/json"})
    with urllib.request.urlopen(request, timeout=300) as reply:
        reply.read()


def opencode_version(opencode_path):
    """OpenCode's version number, like 2.0.29. Run inside HOME: even
    --version writes to OpenCode's log."""
    run = subprocess.run([str(opencode_path), "--version"], env=environment(), capture_output=True,
                         text=True, timeout=30, check=False)
    return run.stdout.strip().removeprefix("opencode").strip().lstrip("v")


def prepare_home(opencode_path=DEFAULT_OPENCODE):
    """A fresh home folder for OpenCode and Hanami with the video's six games
    and an empty ~/Ports, and the script the terminal runs (returned). A
    folder by that name that this script didn't make is left alone."""
    mark = HOME / ".hanami-video"
    if HOME.exists() and not mark.exists():
        sys.exit(f"{HOME} is in the way; move it and run again")
    shutil.rmtree(HOME, ignore_errors=True)
    for folder in (".config/opencode", ".local/share", ".local/state", ".cache", "bin", "Ports"):
        (HOME / folder).mkdir(parents=True)
    mark.touch()
    CONFIG_DIR.mkdir(parents=True)
    CONFIG.write_text(settings_text())
    (HOME / "AGENTS.md").write_text(agents_text())
    (HOME / ".config" / "opencode" / "opencode.json").write_text(json.dumps(opencode_config(), indent=2) + "\n")
    (HOME / ".config" / "opencode" / "tui.json").write_text(json.dumps(TUI_CONFIG, indent=2) + "\n")
    # What the TUI remembers: the sidebar's "Getting started" card (free
    # models, /connect) already closed, this version's highlights seen.
    tui = HOME / ".local" / "state" / "opencode" / "latest" / "tui"
    tui.mkdir(parents=True)
    (tui / "plugin.opencode.sidebar.footer.getting-started.json").write_text('{"dismissed":true}')
    (tui / "highlights.json").write_text(json.dumps({"seen": opencode_version(opencode_path)}))
    (HOME / "bin" / "opencode").symlink_to(opencode_path)
    env = environment()
    exports = " ".join(f"{key}={value}" for key, value in env.items() if key not in ("TERM", "LANG"))
    start = HOME / "bin" / "start"
    start.write_text(f"#!/bin/sh\nexport {exports}\ncd {HOME}\nexec {HOME / 'bin' / 'opencode'} --standalone \"$@\"\n")
    start.chmod(0o755)
    return start


def check():
    """(ok, diff_text): whether config.toml is still TOML, has
    folders = ["~/Ports"] (or the full path) and nothing else changed."""
    before = settings_text()
    after = CONFIG.read_text() if CONFIG.exists() else ""
    diff = "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), "before", "after"))
    try:
        folders = tomllib.loads(after).get("folders")
    except tomllib.TOMLDecodeError:
        return False, diff
    rest = [line for line in after.split("\n") if not line.startswith("folders")]
    same = rest == [line for line in before.split("\n") if not line.startswith("folders")]
    return same and folders in (["~/Ports"], [str(GAMES_DIR)], ["~/Ports/"], [str(GAMES_DIR) + "/"]), diff


# --- Self-test ---------------------------------------------------------------


def transcript(out):
    """(tool names, lines) from `opencode run --format json` output: one line
    per tool call (name and input) or piece of text."""
    tools, lines = [], []
    for line in out.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        part = event.get("part") or {}
        if event.get("type") == "tool_use":
            tools.append(part.get("tool", "?"))
            state = part.get("state") or {}
            lines.append(f"[{tools[-1]}] {json.dumps(state.get('input'))[:300]} -> {state.get('status')}")
        elif event.get("type") == "text":
            lines.append("says: " + part.get("text", "").strip().replace("\n", " ")[:400])
        elif event.get("type") == "error":
            lines.append("error: " + json.dumps(event.get("error"))[:400])
    return tools, lines


def run_once(opencode_path, timeout):
    """One run of the task from a fresh home: (ok, diff, seconds, tool
    names, transcript lines, stderr)."""
    prepare_home(opencode_path)
    args = [str(HOME / "bin" / "opencode"), "run", "--standalone", "--format", "json", PROMPT]
    began = time.monotonic()
    try:
        run = subprocess.run(args, cwd=HOME, env=environment(), capture_output=True,
                             text=True, timeout=timeout, check=False)
        out, err = run.stdout, run.stderr
    except subprocess.TimeoutExpired as late:
        out = late.stdout.decode(errors="replace") if isinstance(late.stdout, bytes) else (late.stdout or "")
        err = f"no answer in {timeout} s"
    took = time.monotonic() - began
    tools, lines = transcript(out)
    ok, diff = check()
    return ok, diff, took, tools, lines, err


def test(count, opencode_path=None, timeout=300):
    opencode_path = opencode_path or os.environ.get("OPENCODE") or DEFAULT_OPENCODE
    make_model()
    wins = 0
    for n in range(count):
        ok, diff, took, tools, lines, err = run_once(opencode_path, timeout)
        wins += ok
        print(f"run {n + 1}: {'ok' if ok else 'FAIL'}, {took:.0f} s, {len(tools)} tool calls")
        for line in lines:
            print("  " + line)
        if not ok:
            print("  " + (diff.strip() or "(config.toml unchanged)").replace("\n", "\n  "))
            if err.strip():
                print("  stderr: " + err.strip()[-1500:])
        sys.stdout.flush()
    print(f"{MODEL}: {wins}/{count}")
    return wins


if __name__ == "__main__":
    if "--test" in sys.argv:
        at = sys.argv.index("--test")
        count = int(sys.argv[at + 1]) if at + 1 < len(sys.argv) else 1
        sys.exit(0 if test(count) * 5 >= count * 4 else 1)
    print(__doc__)
