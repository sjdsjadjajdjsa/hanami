"""Measures Hanami against a large made-up game library, on a virtual
screen, so changes for speed and memory come with numbers.

    cargo build --release
    python3 tools/bench.py
    python3 tools/bench.py --steam 2000 --out after.json

Needs Linux, Xvfb and dbus-run-session. Nothing outside a temporary folder
is read or written: HOME and the XDG folders point into it, and Hanami
never goes online.

What it measures:

- scan: `hanami --list`, the same look through every game source the
  panel does each time it opens, with the time each source took.
- cold start: `hanami` from nothing to the panel's first drawn pixel.
- open: `hanami --toggle` against a running, hidden Hanami, to the first
  drawn pixel, and how long the open itself spent finding games.
- memory and CPU: hidden after start, open with petals falling, and
  hidden again after an open.
"""

import argparse
import ctypes
import ctypes.util
import hashlib
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


def library(home, counts):
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
    write(config / "hanami/config.toml", "online = false\n")

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

    def children(self):
        root, parent, children, n = ctypes.c_ulong(), ctypes.c_ulong(), ctypes.POINTER(ctypes.c_ulong)(), ctypes.c_uint()
        if not self.x.XQueryTree(self.d, self.root, ctypes.byref(root), ctypes.byref(parent), ctypes.byref(children), ctypes.byref(n)):
            return []
        windows = [children[i] for i in range(n.value)]
        if children:
            self.x.XFree(children)
        return windows

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
        for window in self.children():
            attributes = XWindowAttributes()
            if not self.x.XGetWindowAttributes(self.d, window, ctypes.byref(attributes)):
                continue
            if attributes.map_state != IS_VIEWABLE or attributes.width < 100 or self.pid(window) != pid:
                continue
            best = (window, attributes)
        if best is None:
            return False, False
        window, attributes = best
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
        time.sleep(1)
        result["hidden_after_opens"] = memory(pid) | {"cpu_percent": cpu_percent(pid, sample)}
        result["toggle_process"] = summary(toggle)
        result["to_first_pixel"] = summary(drawn)
    finally:
        quit_hanami(binary, env, process)
    text = log.read_text()
    opens = text.split(" show\n")[1:]
    finding = [sum(int(ms) for _, _, ms in LOOKED.findall(chunk)) for chunk in opens]
    result["finding_games_per_open"] = summary(finding, scale=1) if finding else None
    result["sources_ms_per_open"] = per_source("".join(opens))
    return result


def report(results):
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
        if warm["finding_games_per_open"]:
            print(f"finding games on each open   {warm['finding_games_per_open']['median']:>7} ms")
        for source, ms in sorted(warm["sources_ms_per_open"].items(), key=lambda item: -item[1]):
            print(f"  {source:<26} {ms:>7} ms")
        print(f"\n{'':<22}{'RSS MB':>8}{'PSS MB':>8}{'anon MB':>9}{'threads':>9}{'CPU %':>8}")
        for name in ("hidden_at_start", "open", "hidden_after_opens"):
            m = warm[name]
            print(f"{name:<22}{m['rss_mb']:>8}{m['pss_mb']:>8}{m['anon_mb']:>9}{m['threads']:>9}{m['cpu_percent']:>8}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--binary", default=str(ROOT / "target/release/hanami"))
    parser.add_argument("--steam", type=int, default=800, help="Steam games")
    parser.add_argument("--apps", type=int, default=150, help="games in the app menu")
    parser.add_argument("--programs", type=int, default=400, help="other programs in the app menu")
    parser.add_argument("--heroic", type=int, default=300, help="Epic and GOG games in Heroic")
    parser.add_argument("--lutris", type=int, default=100, help="Lutris games")
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
    counts = {key: getattr(args, key) for key in ("steam", "apps", "programs", "heroic", "lutris")}
    xvfb = None
    try:
        print(f"Making a library in {home} ...")
        env = {key: value for key, value in os.environ.items() if not key.startswith(("XDG_", "WAYLAND"))}
        env |= library(home, counts)
        results = {"counts": counts, "scan": scan(binary, env, args.runs)}

        if not args.scan_only:
            display = f":{90 + os.getpid() % 100}"
            xvfb = subprocess.Popen(["Xvfb", display, "-screen", "0", "1920x1080x24", "-nolisten", "tcp"],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(100):
                if Path(f"/tmp/.X11-unix/X{display[1:]}").exists():
                    break
                time.sleep(0.05)
            env["DISPLAY"] = display
            screen = Screen(display)
            results["cold"] = cold(binary, env, screen, max(3, args.runs // 2))
            results["warm"] = warm(binary, env, screen, args.runs, args.sample)

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
