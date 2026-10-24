"""Measures Hanami against a large made-up game library, on a virtual
screen, so changes for speed and memory come with numbers.

    cargo build --release
    python3 tools/bench.py
    python3 tools/bench.py --library typical --out typical.json
    python3 tools/bench.py --steam 2000 --out after.json
    python3 tools/bench.py --note machine="my desktop" --note display_scale=1.25

Needs Linux, Xvfb and dbus-run-session. Nothing outside a temporary folder
is read or written: HOME and the XDG folders point into it, and Hanami
never goes online.

Two made-up libraries: `large` (1,350 games, the default) and `typical`
(200 games). Every game in both has an icon. Counts given by hand win.

What it measures. Internal times come from Hanami's own --verbose log;
external ones are taken from outside, by watching the X screen. None of
them include starting a game: they are about the panel.

- scan (internal and external): `hanami --list`, the same look through
  every game source the panel does, with the time each source took.
- cold start (external): `hanami` from nothing to the panel's first drawn
  pixel.
- open (external): `hanami --toggle` against a running, hidden Hanami, to
  the first drawn pixel, and how long looking for games took around each
  open (internal; it runs after the panel is up).
- hotkey (external): Ctrl+Alt+H sent through XTest to the first drawn
  pixel, read from the X server every millisecond. That is when the pixel
  is in the X server, not when a monitor shows it.
- memory and CPU: hidden after start (the library loaded), open and idle
  with petals falling, and hidden again after opening and hiding (icons
  kept). CPU is a percent of one logical core: one fully used logical
  core is 100 %.

Each saved result says how it was made: version, commit, the machine, the
screen, the library and the petals. What the script can't tell is
"unknown"; --note adds what you know (and wins over what was detected).
"""

import argparse
import ctypes
import ctypes.util
import datetime
import hashlib
import platform
import json
import os
import re
import shutil
import sqlite3
import statistics
import struct
import subprocess
import sys
import tempfile
import time
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TICK = os.sysconf("SC_CLK_TCK")
UNKNOWN = "unknown"

# Made-up libraries. `typical` is the one memory targets are checked
# against; keep it the same so runs compare.
LIBRARIES = {
    "large": {"steam": 800, "apps": 150, "programs": 400, "heroic": 300, "lutris": 100},
    "typical": {"steam": 110, "apps": 30, "programs": 80, "heroic": 40, "lutris": 20},
}


# A made-up library ---------------------------------------------------------


def png(size, seed):
    """A size x size RGBA picture, different per seed, as PNG bytes."""
    rows = bytearray()
    for y in range(size):
        rows.append(0)
        for x in range(size):
            rows += bytes(((x * 7 + seed) % 256, (y * 5 + seed * 3) % 256, (x * y + seed) % 256, 255))

    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(bytes(rows))) + chunk(b"IEND", b"")


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        data = data.encode()
    path.write_bytes(data)


def library(home, counts, petals=24):
    """Steam, app menu, Heroic and Lutris games under `home`; returns the environment that points Hanami at them."""
    config, data, system = home / ".config", home / ".local/share", home / "usr/share"
    env = {
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(config),
        "XDG_DATA_HOME": str(data),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "XDG_STATE_HOME": str(home / ".local/state"),
        "XDG_DATA_DIRS": str(system),
        "PATH": f"{home / 'bin'}:/usr/bin:/bin",
    }
    write(config / "hanami/config.toml", f"online = false\n\n[theme]\npetals = {petals}\n")

    # Steam: two library folders, a 32 px icon per game.
    steam, second = data / "Steam", home / "SteamLibrary"
    write(
        steam / "steamapps/libraryfolders.vdf",
        '"libraryfolders"\n{\n'
        f'\t"0"\n\t{{\n\t\t"path"\t\t"{steam}"\n\t}}\n'
        f'\t"1"\n\t{{\n\t\t"path"\t\t"{second}"\n\t}}\n}}\n',
    )
    for n in range(counts["steam"]):
        app = 100000 + n * 10
        folder = steam if n % 2 else second
        write(
            folder / f"steamapps/appmanifest_{app}.acf",
            f'"AppState"\n{{\n\t"appid"\t\t"{app}"\n\t"Universe"\t\t"1"\n\t"name"\t\t"Steam Game {n}"\n'
            f'\t"StateFlags"\t\t"4"\n\t"installdir"\t\t"Steam Game {n}"\n\t"SizeOnDisk"\t\t"1000000"\n'
            f'\t"buildid"\t\t"1"\n}}\n',
        )
        write(data / f"icons/hicolor/32x32/apps/steam_icon_{app}.png", png(32, n))

    # The app menu: games with themed icons, among many programs that aren't.
    shutil.copy("/usr/share/icons/hicolor/index.theme", write_dir(system / "icons/hicolor"))
    for n in range(counts["apps"]):
        write(
            system / f"applications/menu-game-{n}.desktop",
            f"[Desktop Entry]\nType=Application\nName=Menu Game {n}\nExec=true\n"
            f"Icon=menu-game-{n}\nCategories=Game;ActionGame;\n",
        )
        write(system / f"icons/hicolor/48x48/apps/menu-game-{n}.png", png(48, n))
    for n in range(counts["programs"]):
        write(
            system / f"applications/program-{n}.desktop",
            f"[Desktop Entry]\nType=Application\nName=Program {n}\nExec=true\nIcon=program-{n}\nCategories=Utility;\n",
        )

    # Heroic: Epic and GOG games, each with cached art.
    heroic = config / "heroic"
    epic, gog_library, gog_installed = {}, [], []
    for n in range(counts["heroic"]):
        if n % 2:
            app = f"Epic{n}"
            epic[app] = {"app_name": app, "title": f"Epic Game {n}", "is_dlc": False}
            url = f"https://cdn.example/{app}.jpg"
            write(
                heroic / f"legendaryConfig/legendary/metadata/{app}.json",
                json.dumps({"metadata": {"keyImages": [{"type": "DieselGameBoxTall", "url": url}]}}),
            )
            cached = f"{url}?h=400&resize=1&w=300"
        else:
            app = str(1200000000 + n)
            cached = f"https://gog.example/{app}.jpg"
            gog_library.append({"app_name": app, "title": f"GOG Game {n}", "art_square": cached})
            gog_installed.append({"appName": app, "platform": "linux", "install_path": str(home / f"Games/{app}")})
        write(heroic / "images-cache" / hashlib.sha256(cached.encode()).hexdigest(), png(64, n))
    write(heroic / "legendaryConfig/legendary/installed.json", json.dumps(epic))
    write(heroic / "store_cache/gog_library.json", json.dumps({"games": gog_library}))
    write(heroic / "gog_store/installed.json", json.dumps({"installed": gog_installed}))

    # Lutris: its database, its icons, and a `lutris` to run them with.
    write(home / "bin/lutris", "#!/bin/sh\n")
    (home / "bin/lutris").chmod(0o755)
    db = data / "lutris/pga.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db) as conn:
        conn.executescript(
            "CREATE TABLE games (id INTEGER PRIMARY KEY, name TEXT, slug TEXT, installed INTEGER);"
            "CREATE TABLE categories (id INTEGER PRIMARY KEY, name TEXT);"
            "CREATE TABLE games_categories (game_id INTEGER, category_id INTEGER);"
        )
        for n in range(counts["lutris"]):
            conn.execute("INSERT INTO games VALUES (?, ?, ?, 1)", (n + 1, f"Lutris Game {n}", f"lutris-game-{n}"))
            write(data / f"icons/hicolor/128x128/apps/lutris_lutris-game-{n}.png", png(128, n))
    return env


def write_dir(path):
    path.mkdir(parents=True, exist_ok=True)
    return path


# The virtual screen --------------------------------------------------------


class XWindowAttributes(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_int),
        ("y", ctypes.c_int),
        ("width", ctypes.c_int),
        ("height", ctypes.c_int),
        ("border_width", ctypes.c_int),
        ("depth", ctypes.c_int),
        ("visual", ctypes.c_void_p),
        ("root", ctypes.c_ulong),
        ("c_class", ctypes.c_int),
        ("bit_gravity", ctypes.c_int),
        ("win_gravity", ctypes.c_int),
        ("backing_store", ctypes.c_int),
        ("backing_planes", ctypes.c_ulong),
        ("backing_pixel", ctypes.c_ulong),
        ("save_under", ctypes.c_int),
        ("colormap", ctypes.c_ulong),
        ("map_installed", ctypes.c_int),
        ("map_state", ctypes.c_int),
        ("all_event_masks", ctypes.c_long),
        ("your_event_mask", ctypes.c_long),
        ("do_not_propagate_mask", ctypes.c_long),
        ("override_redirect", ctypes.c_int),
        ("screen", ctypes.c_void_p),
    ]


class XImage(ctypes.Structure):
    _fields_ = [
        ("width", ctypes.c_int),
        ("height", ctypes.c_int),
        ("xoffset", ctypes.c_int),
        ("format", ctypes.c_int),
        ("data", ctypes.POINTER(ctypes.c_ubyte)),
        ("byte_order", ctypes.c_int),
        ("bitmap_unit", ctypes.c_int),
        ("bitmap_bit_order", ctypes.c_int),
        ("bitmap_pad", ctypes.c_int),
        ("depth", ctypes.c_int),
        ("bytes_per_line", ctypes.c_int),
        ("bits_per_pixel", ctypes.c_int),
    ]


IS_VIEWABLE, Z_PIXMAP = 2, 2


class Screen:
    """Finds a process's window on the X display and says whether it is on screen and drawn."""

    def __init__(self, display):
        x = ctypes.CDLL(ctypes.util.find_library("X11"))
        x.XOpenDisplay.restype = ctypes.c_void_p
        x.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x.XDefaultRootWindow.restype = ctypes.c_ulong
        x.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        x.XQueryTree.argtypes = [ctypes.c_void_p, ctypes.c_ulong] + [ctypes.c_void_p] * 4
        x.XGetWindowAttributes.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(XWindowAttributes)]
        x.XInternAtom.restype = ctypes.c_ulong
        x.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        x.XGetWindowProperty.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_long,
                                         ctypes.c_long, ctypes.c_int, ctypes.c_ulong] + [ctypes.c_void_p] * 5
        x.XGetImage.restype = ctypes.POINTER(XImage)
        x.XGetImage.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int, ctypes.c_uint,
                                ctypes.c_uint, ctypes.c_ulong, ctypes.c_int]
        x.XFree.argtypes = [ctypes.c_void_p]
        x.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
        # A window can go away between asking for it and looking at it; Xlib's
        # default answer to that is to end this process.
        self.on_error = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)(lambda *_: 0)
        x.XSetErrorHandler(self.on_error)
        self.x = x
        self.d = x.XOpenDisplay(display.encode())
        if not self.d:
            raise RuntimeError(f"couldn't open display {display}")
        self.root = x.XDefaultRootWindow(self.d)
        self.pid_atom = x.XInternAtom(self.d, b"_NET_WM_PID", 0)
        self.width = 0
        self.xtest = None
        found = ctypes.util.find_library("Xtst")
        if found:
            xtest = ctypes.CDLL(found)
            xtest.XTestFakeKeyEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
            x.XStringToKeysym.restype = ctypes.c_ulong
            x.XStringToKeysym.argtypes = [ctypes.c_char_p]
            x.XKeysymToKeycode.restype = ctypes.c_ubyte
            x.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
            x.XFlush.argtypes = [ctypes.c_void_p]
            self.xtest = xtest

    def press(self, *keys):
        """Holds `keys` down in order and lets go, as a person would; needs XTest."""
        codes = [self.x.XKeysymToKeycode(self.d, self.x.XStringToKeysym(key.encode())) for key in keys]
        for code in codes:
            self.xtest.XTestFakeKeyEvent(self.d, code, 1, 0)
        for code in reversed(codes):
            self.xtest.XTestFakeKeyEvent(self.d, code, 0, 0)
        self.x.XFlush(self.d)

    def children(self, window=None):
        root, parent, children, n = ctypes.c_ulong(), ctypes.c_ulong(), ctypes.POINTER(ctypes.c_ulong)(), ctypes.c_uint()
        window = self.root if window is None else window
        if not self.x.XQueryTree(self.d, window, ctypes.byref(root), ctypes.byref(parent), ctypes.byref(children), ctypes.byref(n)):
            return []
        windows = [children[i] for i in range(n.value)]
        if children:
            self.x.XFree(children)
        return windows

    def windows_of(self, pid):
        """`pid`'s windows: on the root window, or one or two levels down, inside a window manager's frame."""
        found, level = [], self.children()
        for _ in range(3):
            below = []
            for window in level:
                if self.pid(window) == pid:
                    found.append(window)
                else:
                    below += self.children(window)
            level = below
        return found

    def pid(self, window):
        kind, fmt, count, after, value = ctypes.c_ulong(), ctypes.c_int(), ctypes.c_ulong(), ctypes.c_ulong(), ctypes.c_void_p()
        ok = self.x.XGetWindowProperty(self.d, window, self.pid_atom, 0, 1, 0, 0, ctypes.byref(kind), ctypes.byref(fmt),
                                       ctypes.byref(count), ctypes.byref(after), ctypes.byref(value))
        if ok != 0 or not value.value:
            return None
        pid = ctypes.cast(value, ctypes.POINTER(ctypes.c_ulong))[0] if count.value else None
        self.x.XFree(value)
        return pid

    def panel(self, pid):
        """(on screen, drawn) for the biggest window `pid` has on screen."""
        best = None
        for window in self.windows_of(pid):
            attributes = XWindowAttributes()
            if not self.x.XGetWindowAttributes(self.d, window, ctypes.byref(attributes)):
                continue
            if attributes.map_state != IS_VIEWABLE or attributes.width < 100:
                continue
            best = (window, attributes)
        if best is None:
            return False, False
        window, attributes = best
        self.width = attributes.width
        # A few pixels in the middle: the panel is fully see-through until it draws.
        image = self.x.XGetImage(self.d, window, attributes.width // 2 - 2, attributes.height // 2 - 2, 4, 4,
                                 0xFFFFFFFF, Z_PIXMAP)
        if not image:
            return True, False
        size = image.contents.bytes_per_line * image.contents.height
        drawn = any(image.contents.data[i] for i in range(size))
        self.x.XFree(image.contents.data)
        self.x.XFree(image)
        return True, drawn

    def wait(self, pid, drawn=True, gone=False, timeout=10.0):
        """Seconds until the panel is drawn (or gone), polled every millisecond."""
        start = time.perf_counter()
        while time.perf_counter() - start < timeout:
            shown, painted = self.panel(pid)
            if (gone and not shown) or (not gone and (painted if drawn else shown)):
                return time.perf_counter() - start
            time.sleep(0.001)
        raise TimeoutError("the panel never " + ("went away" if gone else "showed up"))


# Reading a process ---------------------------------------------------------


def memory(pid):
    """Resident and proportional memory, in MB."""
    fields = {}
    for line in Path(f"/proc/{pid}/smaps_rollup").read_text().splitlines()[1:]:
        name, value = line.split(":")
        fields[name] = int(value.split()[0]) / 1024
    status = Path(f"/proc/{pid}/status").read_text()
    threads = int(re.search(r"Threads:\s+(\d+)", status).group(1))
    return {
        "rss_mb": round(fields["Rss"], 1),
        "pss_mb": round(fields["Pss"], 1),
        "anon_mb": round(fields["Anonymous"], 1),
        "threads": threads,
    }


def cpu_seconds(pid):
    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    return (int(fields[11]) + int(fields[12])) / TICK


def cpu_percent(pid, seconds):
    before, start = cpu_seconds(pid), time.perf_counter()
    time.sleep(seconds)
    return round(100 * (cpu_seconds(pid) - before) / (time.perf_counter() - start), 2)


def summary(values, unit="ms", scale=1000):
    values = sorted(v * scale for v in values)
    return {
        "median": round(statistics.median(values), 1),
        "min": round(values[0], 1),
        "max": round(values[-1], 1),
        "runs": len(values),
        "unit": unit,
    }


LOOKED = re.compile(r"looked in (\w+): (\d+) games in (\d+) ms")


def per_source(log):
    """Median milliseconds per source from --verbose output."""
    times = {}
    for source, _, ms in LOOKED.findall(log):
        times.setdefault(source, []).append(int(ms))
    return {source: statistics.median(ms) for source, ms in times.items()}


def games_per_source(log):
    return {source: int(count) for source, count, _ in LOOKED.findall(log)}


# How a run was made -----------------------------------------------------


def run_text(*command):
    try:
        done = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def source_value(path, pattern):
    try:
        found = re.search(pattern, (ROOT / path).read_text(), re.MULTILINE)
    except OSError:
        return None
    return found.group(1) if found else None


def meminfo():
    try:
        lines = Path("/proc/meminfo").read_text().splitlines()
    except OSError:
        return {}
    return {line.split(":")[0]: int(line.split()[1]) // 1024 for line in lines}


def machine():
    """What this computer is, as far as Linux says."""
    cpu = UNKNOWN
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    os_name = UNKNOWN
    try:
        os_name = re.search(r'^PRETTY_NAME="?([^"\n]*)', Path("/etc/os-release").read_text(), re.MULTILINE).group(1)
    except (OSError, AttributeError):
        pass
    memory = meminfo()
    virtual = run_text("systemd-detect-virt")
    return {
        "os": f"{os_name}, Linux {platform.release()}",
        "cpu_model": cpu,
        "logical_cores": os.cpu_count() or UNKNOWN,
        "memory_total_mb": memory.get("MemTotal", UNKNOWN),
        "memory_available_mb": memory.get("MemAvailable", UNKNOWN),
        "virtual_machine": virtual if virtual else UNKNOWN,
    }


def conditions(args, counts, binary):
    frame_ms = source_value("hanami/src/main.rs", r"^const FRAME: Duration = Duration::from_millis\((\d+)\);")
    dirty = run_text("git", "status", "--porcelain")
    return {
        "measured_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "app_version": source_value("hanami/Cargo.toml", r'^version = "(.*)"') or UNKNOWN,
        "commit": run_text("git", "rev-parse", "HEAD") or UNKNOWN,
        "local_changes": UNKNOWN if dirty is None else bool(dirty),
        "binary": binary,
        "machine": machine(),
        "display": {
            "server": f"existing X display {args.display}" if args.display else "Xvfb 1920x1080x24, no window manager, no compositor",
            # Filled in from the panel's width once it has drawn.
            "scale": UNKNOWN,
            "renderer": UNKNOWN,
        },
        "library": {
            "preset": args.library,
            "counts": counts,
            "games": UNKNOWN,
            "icons": "every made-up game has one (Steam 32 px, app menu 48 px, Heroic 64 px, Lutris 128 px)",
        },
        "petals": {
            "count": args.petals,
            "on": args.petals > 0,
            "frame_rate_fps": round(1000 / int(frame_ms), 1) if frame_ms else UNKNOWN,
            "frame_rate_source": "FRAME in hanami/src/main.rs of this checkout" if frame_ms else UNKNOWN,
        },
        "cpu": {
            "unit": "percent of one logical core; one fully used logical core is 100",
            "how": "Hanami's own user + system time from /proc/<pid>/stat over the sample; the X server's work is not counted",
            "sample_seconds": args.sample,
            "panel_states": {
                "hidden_at_start": "hidden, 3 s after start, the library loaded",
                "open": "open and idle, 1 s after the first open drew, no input, list at the top",
                "hidden_after_opens": "hidden again after every open and hide, 1 s after the last, icons kept",
            },
        },
        "memory": {
            "unit": "MB (MiB) from /proc/<pid>/smaps_rollup",
            "rss": "resident: everything in memory, shared libraries counted in full",
            "pss": "proportional: shared pages split between the programs using them",
        },
        "timings": {
            "scan": "external: the whole `hanami --list` process; per source: internal, Hanami's log",
            "cold.to_first_pixel": "external: starting `hanami` until the panel's middle has a drawn pixel",
            "warm.to_first_pixel": "external: starting `hanami --toggle` until the hidden panel has a drawn pixel",
            "warm.hotkey_to_first_pixel": "external: Ctrl+Alt+H sent through XTest until the panel has a drawn pixel in the X server",
            "warm.finding_games_per_open": "internal: Hanami's log; it runs after the panel is up",
            "game_launch": "not measured",
        },
        "notes": {},
    }


# The measurements ----------------------------------------------------------


def scan(binary, env, runs):
    times, logs = [], ""
    for _ in range(runs):
        start = time.perf_counter()
        done = subprocess.run([binary, "--list", "--verbose"], env=env, capture_output=True, text=True, check=True)
        times.append(time.perf_counter() - start)
        logs += done.stderr
        listed = len(done.stdout.splitlines())
    return {"total": summary(times), "games": listed, "sources_ms": per_source(logs), "found": games_per_source(logs)}


def quit_hanami(binary, env, process):
    subprocess.run([binary, "--quit"], env=env, capture_output=True)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def cold(binary, env, screen, runs):
    mapped, drawn = [], []
    for _ in range(runs):
        start = time.perf_counter()
        process = subprocess.Popen([binary], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        screen.wait(process.pid, drawn=False)
        mapped.append(time.perf_counter() - start)
        screen.wait(process.pid)
        drawn.append(time.perf_counter() - start)
        quit_hanami(binary, env, process)
    return {"to_window": summary(mapped), "to_first_pixel": summary(drawn)}


def warm(binary, env, screen, runs, sample):
    log = Path(env["HOME"]) / "hanami.log"
    with open(log, "w") as out:
        process = subprocess.Popen([binary, "--hidden", "--verbose"], env=env, stdout=subprocess.DEVNULL, stderr=out)
    pid = process.pid
    result = {}
    try:
        time.sleep(3)
        result["hidden_at_start"] = memory(pid) | {"cpu_percent": cpu_percent(pid, sample)}

        toggle, drawn = [], []
        for n in range(runs):
            start = time.perf_counter()
            subprocess.run([binary, "--toggle"], env=env, check=True)
            toggle.append(time.perf_counter() - start)
            screen.wait(pid)
            drawn.append(time.perf_counter() - start)
            if n == 0:
                time.sleep(1)
                result["open"] = memory(pid) | {"cpu_percent": cpu_percent(pid, sample)}
            else:
                time.sleep(0.3)
            subprocess.run([binary, "--toggle"], env=env, check=True)
            screen.wait(pid, gone=True)
            # Past Hanami's debounce, so the next toggle counts.
            time.sleep(0.4)
        result["hotkey_to_first_pixel"] = hotkey(screen, pid, runs)
        time.sleep(1)
        result["hidden_after_opens"] = memory(pid) | {"cpu_percent": cpu_percent(pid, sample)}
        result["toggle_process"] = summary(toggle)
        result["to_first_pixel"] = summary(drawn)
    finally:
        quit_hanami(binary, env, process)
    text = log.read_text()
    renderer = re.search(r"drawing with (.*)", text)
    result["renderer"] = renderer.group(1) if renderer else UNKNOWN
    opens = text.split(" show\n")[1:]
    finding = [sum(int(ms) for _, _, ms in LOOKED.findall(chunk)) for chunk in opens]
    result["finding_games_per_open"] = summary(finding, scale=1) if finding else None
    result["sources_ms_per_open"] = per_source("".join(opens))
    return result


def hotkey(screen, pid, runs):
    """Ctrl+Alt+H to the first drawn pixel; "unknown" when the key can't be sent or Hanami didn't get it."""
    if screen.xtest is None:
        return UNKNOWN
    drawn = []
    try:
        for _ in range(runs):
            start = time.perf_counter()
            screen.press("Control_L", "Alt_L", "h")
            screen.wait(pid, timeout=3)
            drawn.append(time.perf_counter() - start)
            time.sleep(0.3)
            screen.press("Control_L", "Alt_L", "h")
            screen.wait(pid, gone=True, timeout=3)
            time.sleep(0.4)
    except TimeoutError:
        # Leave the panel hidden, as the measurements after this expect.
        if screen.panel(pid)[0]:
            subprocess.run([screen.binary, "--toggle"], env=screen.env, check=True)
            screen.wait(pid, gone=True)
        return UNKNOWN
    return summary(drawn)


def report(results):
    c = results["conditions"]
    m = c["machine"]
    print(f"\nHanami {c['app_version']}, {c['commit'][:12]}{' with local changes' if c['local_changes'] is True else ''}")
    print(f"{m['cpu_model']}, {m['logical_cores']} logical cores, {m['memory_available_mb']} MB free, {m['os']}")
    print(f"{c['display']['server']}, scale {c['display']['scale']}, drawing with {c['display']['renderer']}")
    print(f"{c['petals']['count']} petals at {c['petals']['frame_rate_fps']} fps; CPU is % of one logical core over {c['cpu']['sample_seconds']} s")
    for key, value in c["notes"].items():
        print(f"{key}: {value}")
    scan = results["scan"]
    print(f"\nGames listed: {scan['games']}  (found: {scan['found']})")
    print(f"hanami --list                {scan['total']['median']:>7} ms  (min {scan['total']['min']}, max {scan['total']['max']})")
    for source, ms in sorted(scan["sources_ms"].items(), key=lambda item: -item[1]):
        print(f"  {source:<26} {ms:>7} ms")
    if "cold" in results:
        cold = results["cold"]
        print(f"cold start to window         {cold['to_window']['median']:>7} ms")
        print(f"cold start to first pixel    {cold['to_first_pixel']['median']:>7} ms")
    if "warm" in results:
        warm = results["warm"]
        print(f"--toggle process             {warm['toggle_process']['median']:>7} ms")
        print(f"--toggle to first pixel      {warm['to_first_pixel']['median']:>7} ms")
        hot = warm["hotkey_to_first_pixel"]
        print(f"hotkey to first pixel        {hot['median'] if hot != UNKNOWN else UNKNOWN:>7} ms")
        if warm["finding_games_per_open"]:
            print(f"looking for games, each open {warm['finding_games_per_open']['median']:>7} ms")
        for source, ms in sorted(warm["sources_ms_per_open"].items(), key=lambda item: -item[1]):
            print(f"  {source:<26} {ms:>7} ms")
        print(f"\n{'':<22}{'RSS MB':>8}{'PSS MB':>8}{'anon MB':>9}{'threads':>9}{'CPU %':>8}")
        for name in ("hidden_at_start", "open", "hidden_after_opens"):
            m = warm[name]
            print(f"{name:<22}{m['rss_mb']:>8}{m['pss_mb']:>8}{m['anon_mb']:>9}{m['threads']:>9}{m['cpu_percent']:>8}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--binary", default=str(ROOT / "target/release/hanami"))
    parser.add_argument("--library", choices=sorted(LIBRARIES), default="large", help="which made-up library")
    parser.add_argument("--steam", type=int, help="Steam games")
    parser.add_argument("--apps", type=int, help="games in the app menu")
    parser.add_argument("--programs", type=int, help="other programs in the app menu")
    parser.add_argument("--heroic", type=int, help="Epic and GOG games in Heroic")
    parser.add_argument("--lutris", type=int, help="Lutris games")
    parser.add_argument("--petals", type=int, default=24, help="petals in the panel (0 for none)")
    parser.add_argument("--display", help="an X display to use instead of starting Xvfb, like :0; quit your own "
                                          "Hanami first, as the timed Ctrl+Alt+H presses go to that whole screen")
    parser.add_argument("--note", action="append", default=[], metavar="KEY=VALUE",
                        help="something about this run the script can't find out, like machine=\"my desktop\" "
                             "or display_scale=1.25; saved with the results")
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--sample", type=float, default=10, help="seconds to measure CPU over")
    parser.add_argument("--scan-only", action="store_true", help="skip everything that needs a screen")
    parser.add_argument("--keep", action="store_true", help="keep the made-up home folder")
    parser.add_argument("--out", help="also write the results as JSON here")
    args = parser.parse_args()

    if not args.scan_only and "BENCH_IN_DBUS" not in os.environ:
        # The tray needs a session bus; give the run a private one.
        os.environ["BENCH_IN_DBUS"] = "1"
        os.execvp("dbus-run-session", ["dbus-run-session", "--", sys.executable] + sys.argv)

    binary = str(Path(args.binary).resolve())
    home = Path(tempfile.mkdtemp(prefix="hanami-bench-"))
    counts = {key: LIBRARIES[args.library][key] if getattr(args, key) is None else getattr(args, key)
              for key in ("steam", "apps", "programs", "heroic", "lutris")}
    notes = {}
    for note in args.note:
        key, _, value = note.partition("=")
        if not value:
            parser.error(f"--note {note}: write it as KEY=VALUE")
        notes[key.strip()] = value.strip()
    xvfb = None
    try:
        print(f"Making a library in {home} ...")
        env = {key: value for key, value in os.environ.items() if not key.startswith(("XDG_", "WAYLAND"))}
        env |= library(home, counts, args.petals)
        results = {"conditions": conditions(args, counts, binary), "counts": counts, "scan": scan(binary, env, args.runs)}
        results["conditions"]["library"]["games"] = results["scan"]["games"]

        if not args.scan_only:
            display = args.display
            if not display:
                display = f":{90 + os.getpid() % 100}"
                xvfb = subprocess.Popen(["Xvfb", display, "-screen", "0", "1920x1080x24", "-nolisten", "tcp"],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                for _ in range(100):
                    if Path(f"/tmp/.X11-unix/X{display[1:]}").exists():
                        break
                    time.sleep(0.05)
            env["DISPLAY"] = display
            screen = Screen(display)
            screen.binary, screen.env = binary, env
            results["cold"] = cold(binary, env, screen, max(3, args.runs // 2))
            results["warm"] = warm(binary, env, screen, args.runs, args.sample)
            shown = results["conditions"]["display"]
            # The panel is 340 px wide at scale 1.
            shown["scale"] = round(screen.width / 340, 2) if screen.width else UNKNOWN
            shown["renderer"] = results["warm"]["renderer"]

        conditions_notes = results["conditions"]["notes"]
        for key, value in notes.items():
            conditions_notes[key] = value
        if "display_scale" in notes:
            results["conditions"]["display"]["scale"] = notes["display_scale"]
        report(results)
        if args.out:
            Path(args.out).write_text(json.dumps(results, indent=2) + "\n")
            print(f"\nWrote {args.out}")
    finally:
        if xvfb:
            xvfb.terminate()
            xvfb.wait()
        if args.keep:
            print(f"Kept {home}")
        else:
            shutil.rmtree(home, ignore_errors=True)


if __name__ == "__main__":
    main()
