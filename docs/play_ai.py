"""The AI side of Hanami's "play" video: a free model running on the
person's own computer (Qwen3 Coder 30B, served by Ollama) in OpenCode, asked
to change Hanami's look: "make it autumn, with maple leaves". Nothing is
scripted here: the model and OpenCode are real, so this only sets the stage.
It doesn't start anything on its own.

    python3 docs/play_ai.py --test 5

runs the task five times with `opencode run`, each from a fresh home folder,
and says how each went.
"""

import difflib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import time
import tomllib
import urllib.request
import zlib
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from seasons_ai import GAMES, SNOW

HOME = Path("/tmp/sam")
OLLAMA = "http://127.0.0.1:11434"
# qwen3-coder:30b with a bigger context: Ollama's default (4096 on a 16 GB
# card) can't even hold OpenCode's system prompt, let alone the guide's
# section. make_model() creates it once.
BASE = "qwen3-coder:30b"
MODEL = "qwen3-coder-hanami"
CONTEXT = 32768
# Qwen's advice for Qwen3 Coder (also what the model file has).
TEMPERATURE = 0.7
MODEL_NAME = "Qwen3 Coder 30B"
PROMPT = "make it autumn, with maple leaves"

CONFIG_DIR = HOME / ".config" / "hanami"
CONFIG = CONFIG_DIR / "config.toml"
PETAL = CONFIG_DIR / "petal.svg"
DEFAULT_OPENCODE = "/usr/bin/opencode"
HANAMI = ROOT / "target" / "release" / "hanami"
SNAPSHOT = Path("/tmp/play-check.png")

# The [theme] the model is expected to write: the autumn row of the table in
# GUIDE.md ("Changing the look"). The guide suggests no panel colours for
# autumn; these are the ones docs/seasons_ai.py uses.
AUTUMN = {
    "panel": "#24170fd0", "text": "#f3e4d0", "dim": "#b08a6a", "accent": "#e8702a",
    "petals": 16, "speed": 0.7, "size": 1.8, "drift": 1.6, "spin": 1.4,
    "tints": ["#e0602a", "#c8401c", "#f0a040", "#9a3410"], "dots": 12,
}
COLOURS = ("panel", "text", "dim", "accent")

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
    top-level settings, with the default file's comments, and no [theme]."""
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


def guide_look():
    """GUIDE.md's "Changing the look", as it is: the [theme] keys, the table
    of settings, the rules for petal.svg and the two example pictures (up to
    the end of the snowflake's)."""
    lines = (ROOT / "GUIDE.md").read_text().split("\n")
    start = next(k for k, line in enumerate(lines) if line.startswith("## Changing the look"))
    snow = next(k for k in range(start, len(lines)) if lines[k].startswith("The snowflake"))
    opening = next(k for k in range(snow, len(lines)) if lines[k].startswith("```svg"))
    end = next(k for k in range(opening + 1, len(lines)) if lines[k].startswith("```"))
    return "\n".join(lines[start : end + 1])


def colours(theme):
    """A look's four panel colours as they'd be written in [theme], like
    `panel = "#24170fd0"`, `text = ...`."""
    return ", ".join(f'`{key} = "{theme[key]}"`' for key in COLOURS)


def agents_text():
    """AGENTS.md in the working folder: where Hanami's two files are and the
    guide's section on them, so the model doesn't go looking."""
    return f"""# This computer

The home folder is {HOME} (`~`).

## Hanami

Hanami is the game launcher. Its settings are in
~/.config/hanami/config.toml ({CONFIG}), a TOML file
that is already there, with the person's games and settings in it. Its
falling shape is ~/.config/hanami/petal.svg ({PETAL}),
which isn't there yet.

To change Hanami's look, three tool calls:

1. read config.toml.
2. edit config.toml: add the `[theme]` block at the very end (old text: the
   file's last line; new text: that line, a blank line, then the block).
   Never use write on config.toml: it would wipe the person's games.
   In the block, use the table's row for the look asked for, and colours
   that go with it. The colours in the guide's example block below are
   sakura's (a pink accent). For autumn: {colours(AUTUMN)}.
   For snow: {colours(SNOW)}.
3. write petal.svg: the guide's example picture for that look, exactly as
   it is.

From Hanami's GUIDE.md:

{guide_look()}

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
                # OpenCode 2.0 doesn't send an agent's temperature to this
                # provider; the model's options it does. The output limit
                # leaves room for the maple leaf's picture in one write.
                "models": {MODEL: {"name": MODEL_NAME, "tool_call": True,
                                   "options": {"temperature": TEMPERATURE},
                                   "limit": {"context": CONTEXT, "output": 8192}}},
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
    and no look of its own, and the script the terminal runs (returned). A
    folder by that name that this script didn't make is left alone."""
    mark = HOME / ".hanami-video"
    if HOME.exists() and not mark.exists():
        sys.exit(f"{HOME} is in the way; move it and run again")
    shutil.rmtree(HOME, ignore_errors=True)
    for folder in (".config/opencode", ".local/share", ".local/state", ".cache", "bin"):
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


# --- Checking the result -----------------------------------------------------

COLOUR = re.compile(r"#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?")


def without_theme(text):
    """The lines of a settings file outside its [theme] block, blank ones
    left out."""
    kept, inside = [], False
    for line in text.split("\n"):
        header = line.strip()
        if header.startswith("["):
            inside = header.replace(" ", "") == "[theme]"
        if not inside and header:
            kept.append(line.rstrip())
    return kept


def theme_problems(theme):
    """What is wrong with a [theme] table, measured against AUTUMN: the
    motion keys and tints must be the guide's, colours must be colours."""
    if not isinstance(theme, dict):
        return ["no [theme] table"]
    problems = []
    for key in ("petals", "speed", "size", "drift", "spin", "dots"):
        value = theme.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or abs(value - AUTUMN[key]) > 1e-9:
            problems.append(f"{key} = {value!r}, the guide says {AUTUMN[key]}")
    tints = theme.get("tints")
    if not isinstance(tints, list) or [str(t).lower() for t in tints] != AUTUMN["tints"]:
        problems.append(f"tints = {tints!r}, the guide says {AUTUMN['tints']}")
    for key in COLOURS:
        if key in theme and not (isinstance(theme[key], str) and COLOUR.fullmatch(theme[key])):
            problems.append(f"{key} = {theme[key]!r} isn't a colour")
    for key in sorted(set(theme) - set(AUTUMN)):
        problems.append(f"{key} isn't one of the guide's keys")
    return problems


def png_pixels(path):
    """(width, height, rows of (r, g, b, a)) of an 8-bit RGBA png, the kind
    rsvg-convert writes."""
    data = path.read_bytes()
    chunks, at = {}, 8
    while at < len(data):
        size, kind = struct.unpack(">I4s", data[at : at + 8])
        chunks[kind] = chunks.get(kind, b"") + data[at + 8 : at + 8 + size]
        at += size + 12
    width, height, depth, colour_type = struct.unpack(">IIBB", chunks[b"IHDR"][:10])
    if (depth, colour_type) != (8, 6):
        raise ValueError(f"png isn't 8-bit RGBA (depth {depth}, type {colour_type})")
    raw, stride, rows, previous = zlib.decompress(chunks[b"IDAT"]), width * 4, [], bytes(width * 4)
    for y in range(height):
        kind, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1 : (y + 1) * (stride + 1)])
        for x in range(stride):
            a, b, c = line[x - 4] if x >= 4 else 0, previous[x], previous[x - 4] if x >= 4 else 0
            if kind == 1:
                line[x] = (line[x] + a) & 255
            elif kind == 2:
                line[x] = (line[x] + b) & 255
            elif kind == 3:
                line[x] = (line[x] + (a + b) // 2) & 255
            elif kind == 4:
                p = a + b - c
                nearest = min((abs(p - a), 0, a), (abs(p - b), 1, b), (abs(p - c), 2, c))[2]
                line[x] = (line[x] + nearest) & 255
        rows.append([tuple(line[x : x + 4]) for x in range(0, stride, 4)])
        previous = bytes(line)
    return width, height, rows


def petal_problems():
    """What is wrong with petal.svg: there, an SVG, drawable, and mostly
    leaf-coloured (red, orange, brown: warm and solid) at 64 pixels."""
    if not PETAL.exists():
        return ["no petal.svg"]
    parse = subprocess.run(
        ["python3", "-c", "import sys, xml.etree.ElementTree as E\n"
         "root = E.parse(sys.argv[1]).getroot()\n"
         "sys.exit(0 if root.tag.rsplit('}', 1)[-1] == 'svg' else 'not an <svg>: ' + root.tag)", str(PETAL)],
        capture_output=True, text=True, timeout=30, check=False)
    if parse.returncode:
        return ["petal.svg isn't SVG: " + (parse.stderr.strip().split("\n")[-1] or parse.stdout.strip())]
    picture = Path("/tmp/play-petal.png")
    draw = subprocess.run(["rsvg-convert", "-w", "64", "-h", "64", "-o", str(picture), str(PETAL)],
                          capture_output=True, text=True, timeout=30, check=False)
    if draw.returncode:
        return ["rsvg-convert can't draw petal.svg: " + draw.stderr.strip()[-300:]]
    width, height, rows = png_pixels(picture)
    warm = sum(1 for row in rows for r, g, b, a in row if a >= 128 and r >= 140 and g <= r and r - b >= 80)
    if warm < width * height * 0.15:
        return [f"petal.svg has {warm} leaf-coloured pixels of {width * height} at 64 px"]
    return []


def snapshot_problems():
    """What Hanami says when it draws the panel with this look: nothing, and
    it should finish. Builds Hanami first if there is no release build."""
    if not HANAMI.exists():
        subprocess.run(["cargo", "build", "--release", "-p", "hanami"], cwd=ROOT, check=True)
    env = {**os.environ, "HOME": str(HOME), "XDG_CONFIG_HOME": str(HOME / ".config")}
    SNAPSHOT.unlink(missing_ok=True)
    run = subprocess.run([str(HANAMI), "--snapshot", str(SNAPSHOT)], env=env, capture_output=True,
                         text=True, timeout=60, check=False)
    said = (run.stdout + run.stderr).strip()
    problems = []
    if run.returncode:
        problems.append(f"hanami --snapshot exited {run.returncode}: {said[-300:]}")
    elif "Couldn't read" in said or "hanami:" in said:
        problems.append("hanami --snapshot says: " + said[-300:])
    return problems


def check():
    """(ok, report): whether config.toml is still TOML with the guide's
    autumn [theme] and nothing else changed, petal.svg is a warm-coloured
    SVG, and Hanami draws the panel with both without a word of complaint.
    The report is what's wrong and the diff of config.toml."""
    before = settings_text()
    after = CONFIG.read_text() if CONFIG.exists() else ""
    diff = "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), "before", "after"))
    problems = []
    try:
        settings = tomllib.loads(after)
    except tomllib.TOMLDecodeError as error:
        settings = None
        problems.append(f"config.toml isn't TOML: {error}")
    if settings is not None:
        problems += theme_problems(settings.get("theme"))
        rest = {key: value for key, value in settings.items() if key != "theme"}
        if rest != tomllib.loads(before) or without_theme(after) != without_theme(before):
            problems.append("config.toml changed outside [theme]")
    problems += petal_problems()
    if settings is not None:
        problems += snapshot_problems()
    report = "\n".join(problems + ([diff.strip() or "(config.toml unchanged)"] if problems else []))
    return not problems, report


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
    """One run of the task from a fresh home: (ok, report, seconds, tool
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
    ok, report = check()
    return ok, report, took, tools, lines, err


def test(count, opencode_path=None, timeout=600):
    opencode_path = opencode_path or os.environ.get("OPENCODE") or DEFAULT_OPENCODE
    make_model()
    wins = 0
    for n in range(count):
        ok, report, took, tools, lines, err = run_once(opencode_path, timeout)
        wins += ok
        print(f"run {n + 1}: {'ok' if ok else 'FAIL'}, {took:.0f} s, {len(tools)} tool calls")
        for line in lines:
            print("  " + line)
        if not ok:
            print("  " + report.replace("\n", "\n  "))
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
