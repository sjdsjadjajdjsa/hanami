"""The AI side of Hanami's "seasons" video: a stand-in for Anthropic's
Messages API that Claude Code (run for real, in the terminal) talks to, and a
throwaway home folder for it. docs/seasons.py imports this; it doesn't start
anything on its own.

Someone asks three times, in one session: "make it autumn, with maple leaves",
"now snow", "back to sakura". For each, the stand-in has Claude Code read
Hanami's settings, then write petal.svg and a [theme] block (or remove them),
then say it's done. Everything is scripted, so the scene plays the same every
time; only Claude Code and its tools are real.

    python3 docs/seasons_ai.py --test

runs Claude Code non-interactively through the three prompts against the
stand-in and checks the files after each one.
"""

import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent

CLAUDE_HOME = Path(tempfile.gettempdir()) / "alex"
STAND_IN_PORT = 47811
DEMO_KEY = "hanami-video-stand-in-key"
PROMPTS = ["make it autumn, with maple leaves", "now snow", "back to sakura"]

CONFIG_DIR = CLAUDE_HOME / ".config" / "hanami"
CONFIG = CONFIG_DIR / "config.toml"
PETAL = CONFIG_DIR / "petal.svg"

# The six games of the video, as docs/video.py writes them (name, label).
GAMES = [
    ("Hades", "epic"),
    ("Celeste", "steam"),
    ("Dead Cells", "steam"),
    ("Hollow Knight", "gog"),
    ("OpenTTD", "port"),
    ("Stardew Valley", "steam"),
]


def settings_text():
    """config.toml exactly as prepare_claude writes it, without a theme."""
    text = 'find = []\nfavourites = ["Hades", "Hollow Knight"]\nonline = false\ncontroller = false\n'
    for name, label in GAMES:
        text += f'\n[[game]]\nname = "{name}"\ncommand = "/usr/bin/true"\nlabel = "{label}"\n'
    return text


# The [theme] values the AI writes: the autumn and snow rows of the table in
# GUIDE.md ("Changing the look"), with panel/text/dim/accent colours to
# match. Keys are the table's; docs/seasons.py hands these to the panel too.
AUTUMN = {
    "panel": "#24170fd0", "text": "#f3e4d0", "dim": "#b08a6a", "accent": "#e8702a",
    "petals": 16, "speed": 0.7, "size": 1.8, "drift": 1.6, "spin": 1.4,
    "tints": ["#e0602a", "#c8401c", "#f0a040", "#9a3410"], "dots": 12,
}
SNOW = {
    "panel": "#0e1a2cb8", "text": "#ffffff", "dim": "#90b4d6", "accent": "#9ad8ff",
    "petals": 18, "speed": 0.6, "size": 1.3, "drift": 1.3, "spin": 0.3,
    "tints": ["#ffffff", "#dceeff", "#bfe0ff"], "dots": 24,
}


def theme_text(theme):
    """A [theme] block (TOML) for config.toml from one of the dicts above."""
    lines = ["", "[theme]"]
    for key, value in theme.items():
        lines.append(f"{key} = {json.dumps(value) if isinstance(value, (str, list)) else value}")
    return "\n".join(lines) + "\n"


THEMES = {"autumn": theme_text(AUTUMN), "snow": theme_text(SNOW)}
SHAPES = {"autumn": ROOT / "notes" / "maple.svg", "snow": ROOT / "notes" / "snow.svg"}

# What the stand-in says and does for each kind of request, in three steps:
# 0: a word and a Read of the settings (Claude Code won't Write a file it
#    hasn't read); 1: the tool calls that change the look; 2: the last word.
PHASES = {
    "autumn": {"first": "Autumn it is.", "last": "Done. Press Ctrl+Alt+H to see it."},
    "snow": {"first": "Snow it is.", "last": "Done. Press Ctrl+Alt+H to see it."},
    "sakura": {"first": "Sakura again.", "last": "Back to sakura. Ctrl+Alt+H."},
}

# What each prompt has had so far: {user text: [step, step, ...]} — the
# stand-in works out the step from the conversation itself, so this is a
# record (for --test and for whoever is watching), not what decides anything.
STATE = {}
PAUSE = 0.04


def phase_of(text):
    """Which look the user text asks for, or None."""
    low = text.lower()
    for name in ("autumn", "snow", "sakura"):
        if name in low:
            return name
    return None


def tool_calls(phase):
    """The tool_use blocks of step 1 for a phase."""
    if phase == "sakura":
        return [
            ("Bash", {"command": f"rm {PETAL}", "description": "Remove the custom petal"}),
            ("Write", {"file_path": str(CONFIG), "content": settings_text()}),
        ]
    return [
        ("Write", {"file_path": str(PETAL), "content": SHAPES[phase].read_text()}),
        ("Write", {"file_path": str(CONFIG), "content": settings_text() + THEMES[phase]}),
    ]


def user_text(message):
    """What the person typed in a user message, without the reminders Claude
    Code adds around it; None when the message is tool results."""
    content = message.get("content")
    if isinstance(content, str):
        texts = [content]
    else:
        if any(block.get("type") == "tool_result" for block in content or []):
            return None
        texts = [block.get("text", "") for block in content or [] if block.get("type") == "text"]
    text = re.sub(r"<system-reminder>.*?</system-reminder>", "", "\n".join(texts), flags=re.S).strip()
    return text or None


def conversation(messages):
    """(last user text, step), read off the conversation itself so the same
    conversation always gets the same answer: step 0 when the last message is
    the person's text, 1 after the Read's result, 2 after the changes'
    results (their tool_use ids say which)."""
    text, step = None, 0
    for message in messages:
        if message.get("role") != "user":
            continue
        got = user_text(message)
        if got is not None:
            text, step = got, 0
            continue
        ids = {block.get("tool_use_id", "") for block in message.get("content") or []
               if block.get("type") == "tool_result"}
        if any(ident.endswith("_read") for ident in ids):
            step = 1
        if any(ident.endswith(("_0", "_1")) for ident in ids):
            step = 2
    return text, step


class StandIn(http.server.BaseHTTPRequestHandler):
    """Answers Claude Code's API calls for the three prompts. Anything else
    (titles, summaries, token counts) gets a short reply or an empty object."""

    def log_message(self, *args):
        pass

    def reply(self, kind, body):
        self.send_response(200)
        self.send_header("content-type", kind)
        self.end_headers()
        self.wfile.write(body)

    def event(self, data):
        self.wfile.write(f"event: {data['type']}\ndata: {json.dumps(data)}\n\n".encode())
        self.wfile.flush()

    def text(self, index, words, pause):
        self.event({"type": "content_block_start", "index": index, "content_block": {"type": "text", "text": ""}})
        for k in range(0, len(words), 3):
            chunk = " ".join(words[k : k + 3]) + (" " if k + 3 < len(words) else "")
            self.event({"type": "content_block_delta", "index": index, "delta": {"type": "text_delta", "text": chunk}})
            time.sleep(pause)
        self.event({"type": "content_block_stop", "index": index})

    def tool(self, index, ident, name, arguments):
        block = {"type": "tool_use", "id": ident, "name": name, "input": {}}
        self.event({"type": "content_block_start", "index": index, "content_block": block})
        self.event({"type": "content_block_delta", "index": index,
                    "delta": {"type": "input_json_delta", "partial_json": json.dumps(arguments)}})
        self.event({"type": "content_block_stop", "index": index})

    def do_GET(self):
        self.reply("application/json", b"{}")

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))) or b"{}")
        if not self.path.startswith("/v1/messages") or "count_tokens" in self.path:
            self.reply("application/json", b'{"input_tokens": 1200}')
            return
        messages = body.get("messages") or []
        text, step = conversation(messages)
        phase = phase_of(text or "")
        tools = {tool.get("name") for tool in body.get("tools") or []}
        main = phase is not None and "Write" in tools
        # Claude Code folds consecutive assistant messages with the same id
        # into one, which would make every step look like the first.
        ident = f"msg_{phase}_{step}" if main else "msg"
        if not body.get("stream"):
            message = {"id": ident, "type": "message", "role": "assistant", "model": body.get("model"),
                       "content": [{"type": "text", "text": "Hanami look"}], "stop_reason": "end_turn",
                       "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 3}}
            self.reply("application/json", json.dumps(message).encode())
            return
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.end_headers()
        self.event({"type": "message_start", "message": {
            "id": ident, "type": "message", "role": "assistant", "model": body.get("model"), "content": [],
            "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 4200, "output_tokens": 1}}})
        stop = "end_turn"
        if not main:
            self.text(0, ["Hanami", "look"], 0)
        else:
            STATE.setdefault(text, []).append(step)
            if step == 0:
                time.sleep(0.6)
                self.text(0, PHASES[phase]["first"].split(" "), PAUSE)
                self.tool(1, f"toolu_{phase}_read", "Read", {"file_path": str(CONFIG)})
                stop = "tool_use"
            elif step == 1:
                time.sleep(0.4)
                for k, (name, arguments) in enumerate(tool_calls(phase)):
                    self.tool(k, f"toolu_{phase}_{k}", name, arguments)
                stop = "tool_use"
            else:
                time.sleep(0.4)
                self.text(0, PHASES[phase]["last"].split(" "), PAUSE)
        self.event({"type": "message_delta", "delta": {"stop_reason": stop, "stop_sequence": None},
                    "usage": {"output_tokens": 100}})
        self.event({"type": "message_stop"})


# Claude Code's permission rules (settings.json): `//` starts an absolute
# path, `**` is any file under it, and a Bash rule without `*` is the exact
# command. Edit rules cover every tool that writes files (Write included);
# a Write(path) rule is ignored, and Claude Code 2.1.299 says so in its
# debug log. These three cover everything the stand-in asks for.
ALLOW = [
    f"Read(//{CONFIG_DIR.relative_to('/')}/**)",
    f"Edit(//{CONFIG_DIR.relative_to('/')}/**)",
    f"Bash(rm {PETAL})",
]


def prepare_claude(claude):
    """A home folder for Claude Code and Hanami with the video's six games,
    and the script the terminal runs (returned). A folder by that name that
    this script didn't make is left alone."""
    mark = CLAUDE_HOME / ".hanami-video"
    if CLAUDE_HOME.exists() and not mark.exists():
        sys.exit(f"{CLAUDE_HOME} is in the way; move it and run again")
    shutil.rmtree(CLAUDE_HOME, ignore_errors=True)
    (CLAUDE_HOME / ".claude").mkdir(parents=True)
    mark.touch()
    CONFIG_DIR.mkdir(parents=True)
    (CLAUDE_HOME / "bin").mkdir()
    (CLAUDE_HOME / "bin" / "hanami").symlink_to(ROOT / "target" / "release" / "hanami")
    (CLAUDE_HOME / ".claude.json").write_text(json.dumps({
        "hasCompletedOnboarding": True, "theme": "dark", "autoUpdates": False, "numStartups": 5,
        "hasSeenAutoDefaultNotice": True, "hasSeenAutoDefaultNudge": True,
        "customApiKeyResponses": {"approved": [DEMO_KEY[-20:]], "rejected": []},
        "projects": {str(CLAUDE_HOME): {"hasTrustDialogAccepted": True, "allowedTools": []}},
    }))
    (CLAUDE_HOME / ".claude" / "settings.json").write_text(
        json.dumps({"permissions": {"allow": ALLOW, "defaultMode": "default"}}, indent=2))
    CONFIG.write_text(settings_text())
    start = CLAUDE_HOME / "bin" / "start"
    start.write_text(
        f"#!/bin/sh\nexport HOME={CLAUDE_HOME} PATH={CLAUDE_HOME / 'bin'}:/usr/bin:/bin ANTHROPIC_API_KEY={DEMO_KEY}"
        f" ANTHROPIC_BASE_URL=http://127.0.0.1:{STAND_IN_PORT} CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1"
        f" DISABLE_AUTOUPDATER=1 DISABLE_TELEMETRY=1\ncd {CLAUDE_HOME}\nexec {CLAUDE_HOME / 'bin' / 'claude'} \"$@\"\n"
    )
    start.chmod(0o755)
    (CLAUDE_HOME / "bin" / "claude").symlink_to(claude)
    return start


def serve():
    """Starts the stand-in on a thread; returns the server."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", STAND_IN_PORT), StandIn)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


# --- Self-test ---------------------------------------------------------------

DEFAULT_CLAUDE = "/tmp/cc/node_modules/@anthropic-ai/claude-code-linux-x64/claude"


def expect(phase):
    """What the files should be after a phase: (petal.svg text or None, has theme)."""
    if phase == "sakura":
        return None, False
    return SHAPES[phase].read_text(), True


def check(phase):
    petal, themed = expect(phase)
    problems = []
    if petal is None:
        if PETAL.exists():
            problems.append(f"{PETAL} still exists")
    elif not PETAL.exists():
        problems.append(f"{PETAL} is missing")
    elif PETAL.read_text() != petal:
        problems.append(f"{PETAL} isn't the {phase} shape")
    if not CONFIG.exists():
        problems.append(f"{CONFIG} is missing")
    else:
        text = CONFIG.read_text()
        if ("[theme]" in text) != themed:
            problems.append(f"{CONFIG} {'lacks' if themed else 'still has'} [theme]")
        if not text.startswith(settings_text()):
            problems.append(f"{CONFIG} lost its settings")
        if themed and not text.endswith(THEMES[phase]):
            problems.append(f"{CONFIG} has the wrong [theme]")
    return problems


def test(claude, timeout=180):
    claude = Path(claude or os.environ.get("CLAUDE") or DEFAULT_CLAUDE)
    if not claude.exists():
        sys.exit(f"no Claude Code at {claude}; set CLAUDE=/path/to/claude")
    server = serve()
    start = prepare_claude(claude)
    failed = False
    try:
        for n, prompt in enumerate(PROMPTS):
            args = [str(start), "-p", "--output-format", "json"] + (["--continue"] if n else []) + [prompt]
            began = time.monotonic()
            try:
                run = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
            except subprocess.TimeoutExpired:
                print(f"FAIL turn {n + 1} {prompt!r}: no answer in {timeout} s")
                failed = True
                break
            took = time.monotonic() - began
            phase = phase_of(prompt)
            problems = check(phase)
            said = ""
            try:
                said = json.loads(run.stdout).get("result", "")
            except (ValueError, AttributeError):
                said = run.stdout.strip()
            print(f"turn {n + 1} {prompt!r}: {took:.1f} s, exit {run.returncode}, steps {STATE.get(prompt)}, said {said!r}")
            if run.returncode != 0 or problems:
                failed = True
                for problem in problems:
                    print("  " + problem)
                if run.stderr.strip():
                    print("  stderr: " + run.stderr.strip()[-2000:])
                if run.returncode != 0:
                    print("  stdout: " + run.stdout.strip()[-2000:])
                break
    finally:
        server.shutdown()
    print("FAIL" if failed else "PASS")
    return not failed


if __name__ == "__main__":
    if "--test" in sys.argv:
        at = sys.argv.index("--test")
        sys.exit(0 if test(sys.argv[at + 1] if at + 1 < len(sys.argv) else None) else 1)
    print(__doc__)
