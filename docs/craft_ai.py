"""The AI side of Hanami's "craft" video: six coding agents, each on a
different model, each asked one thing about the same Hanami, one after the
other. Nothing is scripted here: the agents and the models are real, so this
only sets the stage. It doesn't start anything on its own.

    Crush            Kimi K2.8          hide Dead Cells
    OpenCode         Devstral 24B       rename Stardew Valley to just Stardew
    Antigravity CLI  Gemini 3.8 Flash   pin Hades and Hollow Knight
    jcode            Kimi K3            make it autumn, with maple leaves
    Codex            GPT-5.5            make Ctrl+Space open Hanami
    Claude Code      Claude Opus 5.5    find my Minecraft too

Every agent runs on something the person already has, nothing paid per
use: Claude Code, Codex and jcode on their subscriptions, signed in once each
in a folder of their own (see --login); Crush on the same Kimi membership as
jcode, with its Kimi Code key; Antigravity CLI on their Google subscription,
signed in as they use it (agy, in ~/.local/bin); OpenCode on a free model on
their own Ollama server. The
agents work in one throwaway home folder, so each change builds on the last.

    python3 docs/craft_ai.py --login claude|codex|jcode
    python3 docs/craft_ai.py --test [first] [last]
    python3 docs/craft_ai.py --done N

--login starts that agent in its sign-in folder; --test runs the steps with
each agent's non-interactive mode, from a fresh home folder, and checks the
settings after each one; --done says (by its exit code) whether the
settings are as they should be after step N.
"""

import difflib
import json
import os
import shutil
import subprocess
import sys
import time
import tomllib
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import evening_ai  # noqa: E402
import play_ai  # noqa: E402
from play_ai import AUTUMN, CONFIG, CONFIG_DIR, HOME, PETAL, colours, guide_look  # noqa: E402

CACHE = Path.home() / ".cache" / "hanami-craft"
LOGINS = CACHE / "logins"
TOOLS = CACHE / "tools" / "node_modules"
OLLAMA = play_ai.OLLAMA
HANAMI = ROOT / "target" / "release" / "hanami"

GAMES = [
    ("Hades", "epic"),
    ("Celeste", "steam"),
    ("Dead Cells", "steam"),
    ("Hollow Knight", "gog"),
    ("Stardew Valley", "steam"),
]

# Each step: the agent, the model it runs on as the video names it, what
# the person types, and what config.toml holds afterwards (the keys that
# change; [theme] and petal.svg are checked on their own).
STEPS = [
    {"agent": "crush", "name": "Crush", "model": "Kimi K2.8",
     "prompt": "hide Dead Cells", "set": {"hide": {"dead cells"}}},
    {"agent": "opencode", "name": "OpenCode", "model": "Devstral 24B",
     "prompt": "rename Stardew Valley to just Stardew", "set": {"rename": {"Stardew Valley": "Stardew"}}},
    {"agent": "agy", "name": "Antigravity CLI", "model": "Gemini 3.8 Flash",
     "prompt": "pin Hades and Hollow Knight", "set": {"favourites": {"Hades", "Hollow Knight"}}},
    {"agent": "jcode", "name": "jcode", "model": "Kimi K3",
     "prompt": "make it autumn, with maple leaves", "set": {}, "look": True},
    {"agent": "codex", "name": "Codex", "model": "GPT-5.5",
     "prompt": "make Ctrl+Space open Hanami", "set": {"hotkey": "ctrl+space"}},
    {"agent": "claude", "name": "Claude Code", "model": "Claude Opus 5.5",
     "prompt": "find my Minecraft too", "set": {"find": {"prism"}}},
]

# The models behind the names, as each agent asks for them.
CLAUDE_MODEL = "opus"
KIMI_MODEL = "k3"
KIMI_CODE = "https://api.kimi.com/coding/v1"
CRUSH_MODEL, CRUSH_MODEL_NAME = "kimi-for-coding", "Kimi K2.8"
AGY = Path.home() / ".local" / "bin" / "agy"
AGY_MODEL = "Gemini 3.8 Flash (High)"


def settings_text():
    """config.toml before the first agent: the five games and the usual
    top-level settings, with the default file's comments."""
    text = (
        "# Hanami settings. Changes show up the next time the panel opens.\n\n"
        "# Where Hanami looks for installed games. Remove one to stop looking there.\n"
        "# Linux: steam, heroic (its Epic, GOG and Amazon games), lutris, and apps\n"
        "# (games in your app menu). Windows: steam, epic, gog and heroic. Both:\n"
        "# ports (game ports and rewrites, see folders and projects below) and\n"
        "# prism (each Minecraft instance in Prism Launcher, PolyMC or MultiMC).\n"
        "find = []\n\n"
        "# Games shown at the top of the list, by name.\n"
        "favourites = []\n\n"
        "# Your own names for games: the name Hanami found, then yours.\n"
        "rename = {}\n\n"
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


def guide_section(title):
    """One `## title` section of GUIDE.md, as it is."""
    lines = (ROOT / "GUIDE.md").read_text().split("\n")
    start = next(k for k, line in enumerate(lines) if line == f"## {title}")
    end = next((k for k in range(start + 1, len(lines)) if lines[k].startswith("## ")), len(lines))
    return "\n".join(lines[start:end]).strip()


def look_text():
    """LOOK.md, next to AGENTS.md: the guide's part on the look. Kept out of
    AGENTS.md, which every agent reads, so the small models' context stays
    free for the task."""
    return f"""# Changing Hanami's look

Add a `[theme]` block at the very end of config.toml (old text: the file's
last line; new text: that line, a blank line, then the block), with the
table's row for the look asked for and colours that go with it (for autumn:
{colours(AUTUMN)}). Then write petal.svg: the guide's example picture for
that look, exactly as it is.

{guide_look()}
"""


def agents_text():
    """AGENTS.md in the working folder (also CLAUDE.md and GEMINI.md): where
    Hanami's files are and the parts of its guide about them."""
    return f"""# This computer

The home folder is {HOME} (`~`).

## Hanami

Hanami is the game launcher; every request here is about Hanami. Its settings are in
~/.config/hanami/config.toml ({CONFIG}), a TOML file that is already there,
with the person's games and settings in it. Its falling shape is
~/.config/hanami/petal.svg ({PETAL}), which isn't there until a look needs it.

To change a setting: read config.toml, then edit it, changing only the lines
the request is about (add a key that isn't there yet near the others at the
top, never inside a [[game]] block). Never rewrite the whole file: it would
wipe the person's games.

`hide` leaves a game out of the list, also one written in this file; never
delete a game's [[game]] block to hide it.

The places Hanami can look for games (`find`): steam, heroic, lutris,
apps, epic, gog, ports, and prism (Minecraft: each instance in Prism
Launcher, PolyMC or MultiMC). An empty list means only the games written in
the file.

To change the look, read LOOK.md in this folder first and follow it.

{guide_section("Settings")}

## How to work

Do the task with your tools straight away. Don't write anything before a
tool call: no plan, no "let's", just call the tool. Only when the change is
made, say in one short sentence what you changed.
"""


# --- What the settings should be ----------------------------------------------


def wanted(step):
    """What steps 1..step asked for, merged: {"hide": set, "rename": dict, ...}."""
    want = {}
    for done in STEPS[:step]:
        want.update(done["set"])
    return want


def listed():
    """The games Hanami would show, by name, as `hanami --list` prints them."""
    env = {**os.environ, "HOME": str(HOME), "XDG_CONFIG_HOME": str(HOME / ".config"),
           "XDG_DATA_HOME": str(HOME / ".local" / "share")}
    run = subprocess.run([str(HANAMI), "--list"], env=env, capture_output=True, text=True, timeout=60, check=False)
    return [line.split("\t")[0] for line in run.stdout.splitlines() if line.strip()]


def check(step):
    """(ok, report) after `step` steps: config.toml is still TOML; the
    panel's list has the games it should, under the names asked for (a
    rename can be `rename` or the game's own entry: both are the person's
    to change); pins, hotkey and places are as asked; after the look,
    [theme] and petal.svg are the guide's autumn and Hanami draws them."""
    after = CONFIG.read_text() if CONFIG.exists() else ""
    diff = "".join(difflib.unified_diff(settings_text().splitlines(True), after.splitlines(True), "before", "after"))
    try:
        settings = tomllib.loads(after)
    except tomllib.TOMLDecodeError as error:
        return False, f"config.toml isn't TOML: {error}\n{diff}"
    want, problems = wanted(step), []
    renames = want.get("rename", {})
    shown = {renames.get(name, name) for name, _ in GAMES if name.lower() not in want.get("hide", set())}
    names = listed()
    if not shown <= set(names):
        problems.append(f"the list is missing {sorted(shown - set(names))}")
    gone = {renames.get(name, name) for name, _ in GAMES} - shown
    if gone & set(names):
        problems.append(f"the list still has {sorted(gone & set(names))}")
    pins = set(settings.get("favourites", []))
    if pins != want.get("favourites", set()):
        problems.append(f"favourites are {sorted(pins)}, wanted {sorted(want.get('favourites', set()))}")
    hotkey = settings.get("hotkey", "Ctrl+Alt+H").replace(" ", "").lower()
    if hotkey != want.get("hotkey", "ctrl+alt+h"):
        problems.append(f"hotkey is {hotkey!r}")
    places = set(settings.get("find", []))
    if places != want.get("find", set()):
        problems.append(f"find is {sorted(places)}, wanted {sorted(want.get('find', set()))}")
    original = tomllib.loads(settings_text())
    for key in ("controller", "online"):
        if settings.get(key) != original.get(key):
            problems.append(f"{key} changed")
    if len(settings.get("game", [])) != len(GAMES):
        problems.append("a game entry was added or removed")
    if any(done.get("look") for done in STEPS[:step]):
        problems += play_ai.theme_problems(settings.get("theme"))
        problems += play_ai.petal_problems()
        if not problems:
            problems += play_ai.snapshot_problems()
    elif "theme" in settings or PETAL.exists():
        problems.append("a look appeared before anyone asked for one")
    return not problems, "\n".join(problems + ([diff.strip()] if problems else []))


# --- The agents ------------------------------------------------------------------


def base_environment():
    return {
        "HOME": str(HOME),
        "PATH": f"{HOME / 'bin'}:/usr/bin:/bin",
        "XDG_CONFIG_HOME": str(HOME / ".config"),
        "XDG_DATA_HOME": str(HOME / ".local" / "share"),
        "XDG_STATE_HOME": str(HOME / ".local" / "state"),
        "XDG_CACHE_HOME": str(HOME / ".cache"),
        "XDG_RUNTIME_DIR": str(HOME / ".run"),
        "TERM": os.environ.get("TERM", "xterm-256color"),
        "COLORTERM": "truecolor",
        "LANG": os.environ.get("LANG", "C.UTF-8"),
    }


def signed_in(agent, *paths):
    """Copies an agent's sign-in files from its --login folder into HOME."""
    for path in paths:
        source = LOGINS / agent / path
        if not source.exists():
            sys.exit(f"{agent} isn't signed in ({source} is missing): python3 docs/craft_ai.py --login {agent}")
        target = HOME / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target) if source.is_dir() else shutil.copy(source, target)


def claude_program():
    return TOOLS / "@anthropic-ai" / "claude-code-linux-x64" / "claude"


def setup_claude():
    signed_in("claude", ".claude/.credentials.json")
    account = json.loads((LOGINS / "claude" / ".claude.json").read_text()).get("oauthAccount")
    (HOME / ".claude.json").write_text(json.dumps({
        "hasCompletedOnboarding": True, "theme": "dark", "autoUpdates": False, "numStartups": 5,
        "oauthAccount": account, "hasSeenAutoDefaultNotice": True, "hasSeenAutoDefaultNudge": True,
        "projects": {str(HOME): {"hasTrustDialogAccepted": True, "allowedTools": []}},
    }))
    where = f"//{CONFIG_DIR.relative_to('/')}/**"
    (HOME / ".claude" / "settings.json").write_text(json.dumps(
        {"model": CLAUDE_MODEL, "permissions": {"allow": [f"Read({where})", f"Edit({where})"]}}, indent=2))
    env = {"DISABLE_AUTOUPDATER": "1", "DISABLE_TELEMETRY": "1", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}
    return claude_program(), [], env, lambda prompt: ["-p", "--output-format", "text", prompt]


def setup_codex():
    signed_in("codex", ".codex/auth.json")
    (HOME / ".codex" / "config.toml").write_text(
        'approval_policy = "never"\nsandbox_mode = "workspace-write"\ncheck_for_update_on_startup = false\n\n'
        f'[projects."{HOME}"]\ntrust_level = "trusted"\n\n[notice]\nhide_full_access_warning = true\n'
        "hide_rate_limit_model_nudge = true\n\n[analytics]\nenabled = false\n")
    # Without its background server: one left over from an earlier run
    # would hold the socket.
    return TOOLS / ".bin" / "codex", ["--no-daemon"], {}, lambda prompt: ["exec", "--skip-git-repo-check", prompt]


def setup_jcode():
    signed_in("jcode", ".jcode", ".config/jcode")
    program = (Path.home() / ".local" / "bin" / "jcode").resolve()
    return program, ["--no-update", "-p", "kimi", "-m", KIMI_MODEL], {}, \
        lambda prompt: ["--no-update", "-p", "kimi", "-m", KIMI_MODEL, "run", prompt]


def kimi_key():
    """Shell text that reads the Kimi Code key from jcode's sign-in when the
    terminal starts, so the key is never written anywhere else."""
    env = LOGINS / "jcode" / ".config" / "jcode" / "kimi.env"
    if not env.exists():
        sys.exit(f"jcode isn't signed in to Kimi ({env} is missing): python3 docs/craft_ai.py --login jcode")
    return f"$(sed -n 's/^KIMI_API_KEY=//p' '{env}')"


def setup_crush():
    """Crush on the person's Kimi membership (its Kimi Code key, from
    jcode's sign-in), through Kimi Code's OpenAI-compatible endpoint."""
    folder = HOME / ".config" / "crush"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "crush.json").write_text(json.dumps({
        "$schema": "https://charm.land/crush.json",
        "providers": {"kimi": {
            "name": "Kimi Code", "type": "openai-compat", "base_url": KIMI_CODE, "api_key": "$KIMI_API_KEY",
            "models": [{"id": CRUSH_MODEL, "name": CRUSH_MODEL_NAME, "context_window": 262144,
                        "default_max_tokens": 16384}],
        }},
        "models": {"large": {"model": CRUSH_MODEL, "provider": "kimi"},
                   "small": {"model": CRUSH_MODEL, "provider": "kimi"}},
        "options": {"disable_provider_auto_update": True, "disable_metrics": True},
    }, indent=2))
    env = {"CRUSH_DISABLE_METRICS": "1", "KIMI_API_KEY": kimi_key()}
    return shutil.which("crush"), ["--yolo"], env, lambda prompt: ["run", "--quiet", prompt]


def setup_agy():
    """Antigravity CLI on the person's Google subscription. Its sign-in lives
    in the desktop's keyring, reached over the person's own session bus; its
    settings here are only the model and this folder, trusted, and its
first-run screens are marked done as they are for the person."""
    folder = HOME / ".gemini" / "antigravity-cli"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "settings.json").write_text(json.dumps({"model": AGY_MODEL, "trustedWorkspaces": [str(HOME)]}, indent=2))
    # The first-run screens (theme, terms) the person has already been through.
    mine = Path.home() / ".gemini" / "antigravity-cli"
    (folder / "cache").mkdir(exist_ok=True)
    for done in ("cache/onboarding.json", "cache/default_project_id.txt", "jetski_state.pbtxt", "implicit"):
        if (mine / done).is_dir():
            shutil.copytree(mine / done, folder / done)
        elif (mine / done).exists():
            shutil.copy(mine / done, folder / done)
    env = {"DBUS_SESSION_BUS_ADDRESS": f"unix:path=/run/user/{os.getuid()}/bus"}
    return AGY, ["--mode", "accept-edits"], env, lambda prompt: ["--mode", "accept-edits", "-p", prompt]


def setup_opencode():
    config = evening_ai.opencode_config()
    folder = HOME / ".config" / "opencode"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "opencode.json").write_text(json.dumps(config, indent=2) + "\n")
    (folder / "tui.json").write_text(json.dumps(play_ai.TUI_CONFIG, indent=2) + "\n")
    program = shutil.which("opencode")
    tui = HOME / ".local" / "state" / "opencode" / "latest" / "tui"
    tui.mkdir(parents=True, exist_ok=True)
    (tui / "plugin.opencode.sidebar.footer.getting-started.json").write_text('{"dismissed":true}')
    (tui / "highlights.json").write_text(json.dumps({"seen": play_ai.opencode_version(program)}))
    env = {key: "1" for key in ("OPENCODE_DISABLE_AUTOUPDATE", "OPENCODE_DISABLE_MODELS_FETCH",
                                "OPENCODE_DISABLE_LSP_DOWNLOAD", "OPENCODE_DISABLE_DEFAULT_PLUGINS",
                                "OPENCODE_DISABLE_CLAUDE_CODE")}
    return program, ["--standalone"], env, lambda prompt: ["run", "--standalone", prompt]


SETUPS = {"claude": setup_claude, "codex": setup_codex, "agy": setup_agy, "jcode": setup_jcode,
          "crush": setup_crush, "opencode": setup_opencode}


def prepare_home(agents):
    """A fresh home folder for Hanami with the video's five games and for
    the given agents, with a start script each (bin/start-<agent>), which the
    terminal runs; returns {agent: (start script, its arguments in the
    terminal, its non-interactive arguments for a prompt)}. A folder by that name that this script didn't make is
    left alone."""
    mark = HOME / ".hanami-video"
    if HOME.exists() and not mark.exists():
        sys.exit(f"{HOME} is in the way; move it and run again")
    # Agents' background servers left from an earlier run go first.
    subprocess.run(["pkill", "-f", f"^{HOME}/"], check=False)
    shutil.rmtree(HOME, ignore_errors=True)
    for folder in (".config", ".local/share", ".local/state", ".cache", "bin"):
        (HOME / folder).mkdir(parents=True)
    (HOME / ".run").mkdir(mode=0o700)
    mark.touch()
    CONFIG_DIR.mkdir(parents=True)
    CONFIG.write_text(settings_text())
    (HOME / "AGENTS.md").write_text(agents_text())
    (HOME / "LOOK.md").write_text(look_text())
    for name in ("CLAUDE.md", "GEMINI.md"):
        (HOME / name).symlink_to("AGENTS.md")
    (HOME / "bin" / "hanami").symlink_to(HANAMI)
    starts = {}
    for agent in agents:
        program, args, extra, once = SETUPS[agent]()
        env = {**base_environment(), **extra}
        exports = " ".join(f"{key}=\"{value}\"" for key, value in env.items() if key not in ("TERM", "LANG"))
        start = HOME / "bin" / f"start-{agent}"
        start.write_text(f"#!/bin/sh\nexport {exports}\ncd {HOME}\nexec '{program}' \"$@\"\n")
        start.chmod(0o755)
        starts[agent] = (start, args, once)
    return starts


def toml_value(value):
    if isinstance(value, set):
        value = sorted(value)
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{json.dumps(k)} = {json.dumps(v)}" for k, v in value.items()) + " }"
    return json.dumps(value)


def skip_to(step):
    """Writes what steps 1..step would have written, so a test can start
    later: the changed keys at the top of config.toml and, after the look,
    the guide's autumn [theme] and maple leaf."""
    import seasons_ai

    want = wanted(step)
    lines = [line for line in CONFIG.read_text().split("\n") if not any(line.startswith(f"{key} =") for key in want)]
    text = "".join(f"{key} = {toml_value(value)}\n" for key, value in want.items()) + "\n".join(lines)
    if any(done.get("look") for done in STEPS[:step]):
        text += seasons_ai.theme_text(AUTUMN)
        PETAL.write_text(seasons_ai.SHAPES["autumn"].read_text())
    CONFIG.write_text(text)


# --- Signing in and testing --------------------------------------------------------

LOGIN = {
    "claude": (lambda: [str(claude_program())], "type /login, pick your Claude subscription, then /exit"),
    "codex": (lambda: [str(TOOLS / ".bin" / "codex"), "login"], "sign in with ChatGPT in the browser"),
    "jcode": (lambda: [str(Path.home() / ".local" / "bin" / "jcode"), "login", "kimi"], "sign in to Kimi"),
}


def login(agent):
    """Starts an agent in its sign-in folder (a home folder of its own, so
    the person's real one is untouched) to sign in once."""
    if agent not in LOGIN:
        sys.exit(f"--login takes one of {', '.join(LOGIN)}")
    home = LOGINS / agent
    home.mkdir(parents=True, exist_ok=True)
    env = {key: value for key, value in os.environ.items() if not key.startswith("XDG_") or key == "XDG_RUNTIME_DIR"}
    command, hint = LOGIN[agent]
    print(hint)
    subprocess.run(command(), env={**env, "HOME": str(home)}, cwd=home, check=False)


def test(first=1, last=len(STEPS), timeout=600):
    """Runs steps first..last (counted from 1) with each agent's
    non-interactive mode and checks the settings after each one."""
    steps = STEPS[first - 1 : last]
    starts = prepare_home({step["agent"] for step in steps})
    skip_to(first - 1)
    for n, step in enumerate(steps, first):
        start, _, once = starts[step["agent"]]
        began = time.monotonic()
        try:
            run = subprocess.run([str(start), *once(step["prompt"])], capture_output=True, text=True, timeout=timeout,
                                 stdin=subprocess.DEVNULL, check=False)
            said, err, code = run.stdout.strip(), run.stderr.strip(), run.returncode
        except subprocess.TimeoutExpired:
            said, err, code = "", f"no answer in {timeout} s", -1
        ok, report = check(n)
        print(f"step {n} {step['name']} ({step['model']}) {step['prompt']!r}: {'ok' if ok else 'FAIL'}, "
              f"{time.monotonic() - began:.0f} s, exit {code}")
        print("  says: " + said[-600:].replace("\n", "\n  "))
        if not ok:
            print("  " + report.replace("\n", "\n  "))
            if err:
                print("  stderr: " + err[-1500:].replace("\n", "\n  "))
            print("FAIL")
            return False
        sys.stdout.flush()
    print("PASS")
    return True


if __name__ == "__main__":
    if "--login" in sys.argv:
        login(sys.argv[sys.argv.index("--login") + 1])
    elif "--done" in sys.argv:
        sys.exit(0 if check(int(sys.argv[sys.argv.index("--done") + 1]))[0] else 1)
    elif "--test" in sys.argv:
        numbers = [int(arg) for arg in sys.argv[sys.argv.index("--test") + 1 :]]
        sys.exit(0 if test(*numbers) else 1)
    else:
        print(__doc__)
