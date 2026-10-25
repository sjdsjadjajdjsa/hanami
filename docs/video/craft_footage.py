"""Records the Minecraft footage for Hanami's "craft" video: the game as it
starts (the Mojang screen, then the title screen) and a short walk through a
cherry grove. Minecraft runs for real, through Prism Launcher (the Flatpak),
signed in with your own account, in an off-screen KWin session with its own
home folder: a copy of Prism's data, so your instances and settings stay as
they are. The world is made once by Mojang's own server, from a seed, with the
spawn moved into a cherry grove, the sun stopped at noon and no mobs.

    python3 docs/craft_footage.py

Writes title.mp4 and walk.mp4 (1920 x 1080, 60 fps) to
~/.cache/hanami-craft/footage. Needs Prism Launcher from Flathub with a
Minecraft instance that has started once (the newest is used) and a signed-in
account; KDE Plasma (KWin, PipeWire, Spectacle), GStreamer with its Python
bindings, a C compiler with wayland-client and wayland-scanner, ffmpeg and
curl. Running the server means agreeing to the Minecraft EULA
(https://aka.ms/MinecraftEULA), which you did when you bought the game.
"""

import json
import math
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

CACHE = Path.home() / ".cache" / "hanami-craft"
TOOLS = CACHE / "tools" / "cast"
FOOTAGE = CACHE / "footage"
WORLD = CACHE / "world"
PRISM_ID = "org.prismlauncher.PrismLauncher"
PRISM = Path.home() / ".var" / "app" / PRISM_ID
PRISM_DATA = PRISM / "data" / "PrismLauncher"
SEED = "hanami"
WORLD_NAME = "Hanami"
FPS = 60
PROTOCOLS = "https://raw.githubusercontent.com/KDE/plasma-wayland-protocols/master/src/protocols/"

# Two small Wayland programs. KWin only offers these protocols to programs a
# desktop file names, which the session sets up. `cast` asks KWin for a
# PipeWire stream of the screen and prints its node; `drive` reads input
# from stdin: k <evdev key> <1|0>, m <dx> <dy> (relative pointer), w <seconds>.
CAST_C = r"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wayland-client.h>
#include "screencast.h"
static struct zkde_screencast_unstable_v1 *cast;
static void global(void *d, struct wl_registry *r, uint32_t name, const char *iface, uint32_t v) {
    if (strcmp(iface, zkde_screencast_unstable_v1_interface.name) == 0)
        cast = wl_registry_bind(r, name, &zkde_screencast_unstable_v1_interface, v < 4 ? v : 4);
}
static void global_remove(void *d, struct wl_registry *r, uint32_t n) {}
static const struct wl_registry_listener listener = {global, global_remove};
static void closed(void *d, struct zkde_screencast_stream_unstable_v1 *s) { exit(2); }
static void created(void *d, struct zkde_screencast_stream_unstable_v1 *s, uint32_t node) {
    printf("%u\n", node);
    fflush(stdout);
}
static void failed(void *d, struct zkde_screencast_stream_unstable_v1 *s, const char *error) {
    fprintf(stderr, "%s\n", error);
    exit(3);
}
static const struct zkde_screencast_stream_unstable_v1_listener stream = {closed, created, failed};
int main(int argc, char **argv) {
    struct wl_display *display = wl_display_connect(NULL);
    if (!display || argc != 3) return 1;
    struct wl_registry *registry = wl_display_get_registry(display);
    wl_registry_add_listener(registry, &listener, NULL);
    wl_display_roundtrip(display);
    if (!cast) return 4;
    struct zkde_screencast_stream_unstable_v1 *s = zkde_screencast_unstable_v1_stream_region(
        cast, 0, 0, atoi(argv[1]), atoi(argv[2]), wl_fixed_from_int(1), 1);
    zkde_screencast_stream_unstable_v1_add_listener(s, &stream, NULL);
    while (wl_display_dispatch(display) != -1) {}
    return 0;
}
"""
DRIVE_C = r"""
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <wayland-client.h>
#include "fake-input.h"
static struct org_kde_kwin_fake_input *fake;
static void global(void *d, struct wl_registry *r, uint32_t name, const char *iface, uint32_t v) {
    if (strcmp(iface, org_kde_kwin_fake_input_interface.name) == 0)
        fake = wl_registry_bind(r, name, &org_kde_kwin_fake_input_interface, v < 4 ? v : 4);
}
static void global_remove(void *d, struct wl_registry *r, uint32_t n) {}
static const struct wl_registry_listener listener = {global, global_remove};
int main(void) {
    struct wl_display *display = wl_display_connect(NULL);
    if (!display) return 1;
    struct wl_registry *registry = wl_display_get_registry(display);
    wl_registry_add_listener(registry, &listener, NULL);
    wl_display_roundtrip(display);
    if (!fake) return 2;
    org_kde_kwin_fake_input_authenticate(fake, "drive", "walk through the video's world");
    char line[128];
    while (fgets(line, sizeof line, stdin)) {
        double a = 0, b = 0;
        if (sscanf(line + 1, "%lf %lf", &a, &b) < 1) continue;
        if (line[0] == 'k') org_kde_kwin_fake_input_keyboard_key(fake, (uint32_t)a, (uint32_t)b);
        if (line[0] == 'm') org_kde_kwin_fake_input_pointer_motion(fake, wl_fixed_from_double(a), wl_fixed_from_double(b));
        if (line[0] == 'w') { wl_display_flush(display); usleep((useconds_t)(a * 1e6)); }
        wl_display_flush(display);
    }
    wl_display_roundtrip(display);
    return 0;
}
"""
PROGRAMS = {
    "cast": (CAST_C, "zkde-screencast-unstable-v1", "screencast", "zkde_screencast_unstable_v1"),
    "drive": (DRIVE_C, "fake-input", "fake-input", "org_kde_kwin_fake_input"),
}


def build_tools():
    """Compiles `cast` and `drive` into TOOLS, once."""
    TOOLS.mkdir(parents=True, exist_ok=True)
    for name, (source, protocol, header, _) in PROGRAMS.items():
        if (TOOLS / name).exists():
            continue
        xml = TOOLS / f"{protocol}.xml"
        if not xml.exists():
            subprocess.run(["curl", "-sfL", "-o", str(xml), PROTOCOLS + f"{protocol}.xml"], check=True)
        subprocess.run(["wayland-scanner", "client-header", str(xml), str(TOOLS / f"{header}.h")], check=True)
        subprocess.run(["wayland-scanner", "private-code", str(xml), str(TOOLS / f"{header}.c")], check=True)
        (TOOLS / f"{name}.c").write_text(source)
        subprocess.run(["gcc", "-O2", "-o", str(TOOLS / name), str(TOOLS / f"{name}.c"), str(TOOLS / f"{header}.c"),
                        "-lwayland-client", "-lm"], cwd=TOOLS, check=True)


# --- The instance and the world ------------------------------------------------


def instance():
    """The newest Minecraft instance in Prism's Flatpak data: (folder name, Minecraft version)."""
    found = []
    for cfg in (PRISM_DATA / "instances").glob("*/instance.cfg"):
        pack = json.loads((cfg.parent / "mmc-pack.json").read_text())
        version = next((c.get("version") for c in pack.get("components", []) if c.get("uid") == "net.minecraft"), None)
        if version:
            found.append((cfg.stat().st_mtime, cfg.parent.name, version))
    if not found:
        sys.exit(f"no Minecraft instance in {PRISM_DATA}; make one in Prism Launcher and start it once")
    _, name, version = max(found)
    return name, version


def java():
    """The Java Prism downloaded for the game."""
    runtimes = sorted((PRISM_DATA / "java").glob("*/bin/java"))
    if not runtimes:
        sys.exit("Prism hasn't downloaded Java yet; start the instance once")
    return runtimes[-1]


def server_jar(version):
    jar = WORLD / f"server-{version}.jar"
    if jar.exists():
        return jar
    manifest = json.loads(subprocess.run(
        ["curl", "-sf", "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"],
        capture_output=True, check=True).stdout)
    url = next(v["url"] for v in manifest["versions"] if v["id"] == version)
    package = json.loads(subprocess.run(["curl", "-sf", url], capture_output=True, check=True).stdout)
    subprocess.run(["curl", "-sfL", "-o", str(jar), package["downloads"]["server"]["url"]], check=True)
    return jar


def make_world(version):
    """The video's world, made by Mojang's server from SEED: spawn on the
    ground of the nearest cherry grove, noon for ever, clear skies, no mobs."""
    if (WORLD / WORLD_NAME / "level.dat").exists():
        return WORLD / WORLD_NAME
    WORLD.mkdir(parents=True, exist_ok=True)
    jar = server_jar(version)
    (WORLD / "eula.txt").write_text("eula=true\n")
    (WORLD / "server.properties").write_text(
        f"level-seed={SEED}\nlevel-name={WORLD_NAME}\nonline-mode=false\nserver-port=25599\n"
        "spawn-protection=0\nview-distance=8\nsimulation-distance=8\nspawn-monsters=false\n")
    server = subprocess.Popen([str(java()), "-Xmx4G", "-jar", str(jar), "nogui"], cwd=WORLD, text=True, bufsize=1,
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines = []
    threading.Thread(target=lambda: lines.extend(line.rstrip() for line in server.stdout), daemon=True).start()

    def wait_for(pattern, since=0, timeout=300):
        end = time.time() + timeout
        while time.time() < end:
            for line in lines[since:]:
                if found := re.search(pattern, line):
                    return found
            time.sleep(0.2)
        server.kill()
        sys.exit(f"the server never said {pattern!r}:\n" + "\n".join(lines[-20:]))

    def command(text, answer):
        since = len(lines)
        server.stdin.write(text + "\n")
        server.stdin.flush()
        return wait_for(answer, since, 120)

    wait_for(r"Done \(")
    at = command("locate biome minecraft:cherry_grove", r"is at \[(-?\d+), -?[~\d]+, (-?\d+)\]")
    x, z = at.group(1), at.group(2)
    command(f"forceload add {x} {z}", "force loaded")
    command(f"execute positioned {x} 0 {z} positioned over motion_blocking_no_leaves run setworldspawn ~ ~ ~",
            "Set the world spawn")
    for rule, value in (("respawn_radius", 0), ("advance_time", "false"), ("advance_weather", "false"),
                        ("spawn_mobs", "false")):
        command(f"gamerule {rule} {value}", f"Game rule {rule} is now set")
    command("time set 6000", "Set ")
    command("weather clear", "weather")
    command("save-all flush", "Saved the game")
    server.stdin.write("stop\n")
    server.stdin.flush()
    server.wait(120)
    return WORLD / WORLD_NAME


# --- Recording ------------------------------------------------------------------

# Minecraft as it comes, minus what would get in the way of a clean shot:
# the tutorial hints, the first-start accessibility screen and the
# multiplayer warning; full screen at up to 120 fps for smooth capture.
OPTIONS = {
    "fullscreen": "true", "tutorialStep": "none", "onboardAccessibility": "false",
    "skipMultiplayerWarning": "true", "joinedFirstServer": "true", "pauseOnLostFocus": "false",
    "narrator": "0", "guiScale": "0", "renderDistance": "16", "graphicsPreset": '"fancy"',
    "maxFps": "120", "enableVsync": "false", "rawMouseInput": "false", "mouseSensitivity": "0.5",
    "fov": "0.25", "bobView": "true",
}
# Prism shows its log window while a game runs; not in the video.
PRISM_SETTINGS = {"ShowConsole": "false", "AutoCloseConsole": "true", "ShowConsoleOnError": "false"}
# Keys, as evdev codes.
F1, W = 59, 17


def walk():
    """The walk, as `drive` input: F1 hides the hand and the hotbar; the
    view turns right to the best of the grove (seen from the spawn of the
    seed above) and tips up a little; then a slow 90° turn to the right,
    eased in and out, with a few steps forward in the middle of it."""
    lines = ["w 1", f"k {F1} 1", "w 0.05", f"k {F1} 0"]
    lines += ["m 45 -1.7\nw 0.01"] * 30
    lines.append("w 2")
    step, length = 1 / FPS, 14
    for n in range(int(length * FPS)):
        t = n * step
        speed = 600 / length * (1 - math.cos(2 * math.pi * t / length))
        lines += [f"m {speed * step:.4f} 0", f"w {step:.4f}"]
        if abs(t - 4) < step / 2:
            lines.append(f"k {W} 1")
        if abs(t - 9) < step / 2:
            lines.append(f"k {W} 0")
    lines.append("w 1")
    return "\n".join(lines) + "\n"


SESSION = """#!/bin/sh
pipewire > '{place}/pipewire.log' 2>&1 &
sleep 1
wireplumber > '{place}/wireplumber.log' 2>&1 &
sleep 2
flatpak run {prism} --launch '{instance}' {world} > '{place}/prism.log' 2>&1 &
{ready}
'{tools}/cast' 1920 1080 > '{place}/node' &
cast=$!
sleep 1
python3 '{me}' --record $(head -1 '{place}/node') '{out}' &
recorder=$!
sleep 1
{act}
kill -INT $recorder
wait $recorder
kill $cast
"""


def prism_home(home, name, fullscreen):
    """Copies Prism's Flatpak data (the sign-in, the instances, the game's
    files) into `home`, without the log window and with OPTIONS for
    instance `name`; windowed, its window is 1920 x 1080 pixels. Returns the
    instance's game folder."""
    prism = home / ".var" / "app" / PRISM_ID
    shutil.copytree(PRISM, prism, symlinks=True)
    data = prism / "data" / "PrismLauncher"
    settings = data / "prismlauncher.cfg"
    text = re.sub(rf"^({'|'.join(PRISM_SETTINGS)})=.*\n", "", settings.read_text(), flags=re.M)
    extra = "".join(f"{key}={value}\n" for key, value in PRISM_SETTINGS.items())
    settings.write_text(text.replace("[General]\n", "[General]\n" + extra, 1) if "[General]\n" in text else extra + text)
    cfg = data / "instances" / name / "instance.cfg"
    window = {"OverrideWindow": "true", "MinecraftWinWidth": "1920", "MinecraftWinHeight": "1080", "LaunchMaximised": "false"}
    text = re.sub(rf"^({'|'.join(window)})=.*\n", "", cfg.read_text(), flags=re.M)
    cfg.write_text(text.replace("[General]\n", "[General]\n" + "".join(f"{k}={v}\n" for k, v in window.items()), 1))
    game = data / "instances" / name / "minecraft"
    options = (game / "options.txt").read_text() if (game / "options.txt").exists() else ""
    for key, value in {**OPTIONS, "fullscreen": "true" if fullscreen else "false"}.items():
        options, found = re.subn(rf"^{key}:.*$", f"{key}:{value}", options, flags=re.M)
        if not found:
            options += f"{key}:{value}\n"
    (game / "options.txt").write_text(options)
    return game


def record(kind, out):
    """Records Minecraft starting ("title": 45 s from launch) or the walk
    ("walk": from a few seconds after the world has loaded) to `out`."""
    name, _ = instance()
    place = CACHE / "session"
    shutil.rmtree(place, ignore_errors=True)
    home, run = place / "home", place / "run"
    (home / ".config").mkdir(parents=True)
    run.mkdir(mode=0o700)
    apps = home / ".local" / "share" / "applications"
    apps.mkdir(parents=True)
    for program, (_, _, _, interface) in PROGRAMS.items():
        (apps / f"{program}.desktop").write_text(
            f"[Desktop Entry]\nType=Application\nName={program}\nExec={TOOLS / program}\nNoDisplay=true\n"
            f"X-KDE-Wayland-Interfaces={interface}\n")
    game = prism_home(home, name, fullscreen=True)
    log = game / "logs" / "latest.log"
    log.unlink(missing_ok=True)
    if kind == "walk":
        shutil.copytree(WORLD / WORLD_NAME, game / "saves" / WORLD_NAME, dirs_exist_ok=True)
        (place / "walk.txt").write_text(walk())
        ready = (f"n=0; until grep -q 'joined the game' '{log}' 2>/dev/null || [ $n -gt 300 ]; do sleep 1; n=$((n+1)); done\n"
                 "sleep 8")
        act = f"'{TOOLS}/drive' < '{place}/walk.txt'"
    else:
        ready, act = "sleep 2", "sleep 45"
    session = place / "session.sh"
    session.write_text(SESSION.format(
        place=place, prism=PRISM_ID, instance=name, world=f"--world {WORLD_NAME}" if kind == "walk" else "",
        ready=ready, tools=TOOLS, me=Path(__file__).resolve(), out=out, act=act))
    session.chmod(0o755)
    env = {
        "HOME": str(home), "XDG_RUNTIME_DIR": str(run), "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_DATA_HOME": str(home / ".local" / "share"), "XDG_CACHE_HOME": str(home / ".cache"),
        "XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "KDE", "KDE_FULL_SESSION": "true",
        "KDE_SESSION_VERSION": "6", "PATH": "/usr/bin:/bin", "LANG": "en_US.UTF-8",
    }
    subprocess.run(["dbus-run-session", "--", "kwin_wayland", "--virtual", "--width", "1920", "--height", "1080",
                    "--xwayland", "--no-lockscreen", "--exit-with-session", str(session)],
                   env=env, cwd=home, timeout=900, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    shutil.rmtree(place, ignore_errors=True)
    if not out.exists():
        sys.exit(f"could not record the {kind}")


def recorder(node, out):
    """Records a PipeWire video node to `out` at a steady 60 fps until
    SIGINT: each tick gets the newest frame that arrived, so a still picture
    still fills time. Lossless, and fast enough to keep up."""
    import signal

    import gi

    gi.require_version("Gst", "1.0")
    from gi.repository import GLib, GLibUnix, Gst

    Gst.init(None)
    pipe = Gst.parse_launch(
        f"pipewiresrc path={node} always-copy=true ! videoconvert n-threads=4 ! video/x-raw,format=BGRx ! "
        "appsink name=sink emit-signals=true max-buffers=4 drop=false sync=false")
    state = {"ffmpeg": None, "start": 0.0, "ticks": 0, "last": None, "size": None}

    def fill(until):
        while state["start"] + state["ticks"] / FPS < until:
            state["ffmpeg"].stdin.write(state["last"])
            state["ticks"] += 1

    def sample(sink):
        got = sink.emit("pull-sample")
        now = time.monotonic()
        caps = got.get_caps().get_structure(0)
        size = caps.get_value("width"), caps.get_value("height")
        buffer = got.get_buffer()
        ok, info = buffer.map(Gst.MapFlags.READ)
        data = bytes(info.data)
        buffer.unmap(info)
        if state["ffmpeg"] is None:
            state["size"], state["start"] = size, now
            state["ffmpeg"] = subprocess.Popen(
                ["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr0", "-s", f"{size[0]}x{size[1]}",
                 "-r", str(FPS), "-i", "-", "-c:v", "libx264rgb", "-preset", "ultrafast", "-qp", "0", str(out)],
                stdin=subprocess.PIPE)
        elif size != state["size"]:
            return Gst.FlowReturn.OK
        if state["last"] is not None:
            fill(now)
        state["last"] = data
        return Gst.FlowReturn.OK

    pipe.get_by_name("sink").connect("new-sample", sample)
    loop = GLib.MainLoop()

    def stop():
        pipe.set_state(Gst.State.NULL)
        if state["ffmpeg"]:
            fill(time.monotonic())
            state["ffmpeg"].stdin.close()
            state["ffmpeg"].wait()
        loop.quit()
        return False

    GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, stop)
    pipe.set_state(Gst.State.PLAYING)
    loop.run()


def finish(raw, out):
    """The lossless recording, made small: H.264 at a quality nothing in the
    video's own encode can tell apart."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-c:v", "libx264", "-preset", "slow", "-crf", "10",
                    "-pix_fmt", "yuv444p", "-r", str(FPS), str(out)], check=True)
    raw.unlink()


def main():
    if not (PRISM_DATA / "accounts.json").exists():
        sys.exit("needs Prism Launcher from Flathub, signed in to a Microsoft account")
    name, version = instance()
    print(f"Minecraft {version} (instance {name})")
    build_tools()
    print("making the world")
    make_world(version)
    FOOTAGE.mkdir(parents=True, exist_ok=True)
    for kind in ("title", "walk"):
        print(f"recording the {kind}")
        raw = FOOTAGE / f"{kind}.mkv"
        record(kind, raw)
        finish(raw, FOOTAGE / f"{kind}.mp4")
    print(FOOTAGE)


if __name__ == "__main__":
    if sys.argv[1:2] == ["--record"]:
        recorder(sys.argv[2], Path(sys.argv[3]))
    else:
        main()
