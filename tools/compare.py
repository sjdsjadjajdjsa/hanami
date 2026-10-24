"""Runs the same benchmark against past Hanami releases, so the repo can show
CPU, memory and opening time over versions.

    python3 tools/compare.py                      # every release tag and HEAD
    python3 tools/compare.py v0.2.12 v0.2.13 HEAD --rounds 1 --sample 3
    python3 tools/compare.py --build-only         # just build, nothing timed
    python3 tools/compare.py --report results/history/history.json

Each ref is built once, from its own `git worktree add --detach` checkout,
into a cache folder (~/.cache/hanami-compare unless --builds says
otherwise). The build folder is shared between refs, so a ref only builds
what changed since the last one; the binary is copied out per commit and
reused next time. A ref that doesn't build is recorded with the reason.
The shared build folder grows to about 3.5 GB; once every binary is built it
can be deleted (<builds>/target).

tools/bench.py from this checkout measures every binary with the same
settings. Versions take turns, round after round, the order reversed every
other round, so a machine that slowly gets busier or cooler doesn't favour
one version. Per metric the median over rounds is kept, with min and max.

Older versions can't do everything bench.py asks for. What each version
can do is read from its own source (main.rs and config.rs at that commit),
bench.py is told, and what still can't be measured is saved as "unknown"
with the reason.

Writes history.json (everything), history.md (a table) and history.svg
(a chart) to --out-dir.
"""

import argparse
import datetime
import getpass
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
import bench  # noqa: E402  (for machine() and the default config)

UNKNOWN = "unknown"

# What gets compared: (key, path in bench.py's result, label, unit).
METRICS = [
    ("games", ("scan", "games"), "games listed", ""),
    ("list_ms", ("scan", "total", "median"), "hanami --list", "ms"),
    ("cold_first_pixel_ms", ("cold", "to_first_pixel", "median"), "cold start to first pixel", "ms"),
    ("toggle_first_pixel_ms", ("warm", "to_first_pixel", "median"), "--toggle to first pixel", "ms"),
    ("hotkey_first_pixel_ms", ("warm", "hotkey_to_first_pixel", "median"), "Ctrl+Alt+H to first pixel", "ms"),
    ("finding_games_per_open_ms", ("warm", "finding_games_per_open", "median"), "looking for games, each open", "ms"),
    ("cpu_hidden_start", ("warm", "hidden_at_start", "cpu_percent"), "CPU hidden at start", "%"),
    ("cpu_open", ("warm", "open", "cpu_percent"), "CPU open", "%"),
    ("cpu_hidden_after", ("warm", "hidden_after_opens", "cpu_percent"), "CPU hidden after opening", "%"),
    ("rss_hidden_start", ("warm", "hidden_at_start", "rss_mb"), "RSS hidden at start", "MB"),
    ("rss_open", ("warm", "open", "rss_mb"), "RSS open", "MB"),
    ("rss_hidden_after", ("warm", "hidden_after_opens", "rss_mb"), "RSS hidden after opening", "MB"),
    ("pss_hidden_after", ("warm", "hidden_after_opens", "pss_mb"), "PSS hidden after opening", "MB"),
]

# The chart: one panel each.
CHART = [
    ("cpu_open", "CPU while open, petals falling (% of one core)"),
    ("rss_hidden_after", "Memory hidden after opening (RSS, MB)"),
    ("toggle_first_pixel_ms", "--toggle to first pixel (ms)"),
]


def git(*args, cwd=ROOT, check=True):
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {done.stderr.strip()}")
    return done.stdout.strip() if done.returncode == 0 else None


def default_refs():
    tags = git("tag", "--list", "v*").split()
    tags.sort(key=lambda tag: [int(n) for n in re.findall(r"\d+", tag)])
    return tags + ["HEAD"]


# What a version can do, read from its source ------------------------------


def show(commit, path):
    return git("show", f"{commit}:{path}", check=False) or ""


def capabilities(commit):
    main = show(commit, "hanami/src/main.rs")
    # Settings live in config.rs; the [theme] ones moved to theme.rs in 0.2.9.
    config = show(commit, "hanami/src/config.rs") + show(commit, "hanami/src/theme.rs")
    frame = re.search(r"^const FRAME: Duration = Duration::from_millis\((\d+)\);", main, re.MULTILINE)
    fixed_petals = re.search(r"^const PETALS: usize = (\d+);", main + show(commit, "hanami/src/petals.rs"), re.MULTILINE)
    if not fixed_petals:
        fixed_petals = re.search(r"The same (\d+) petals", main + show(commit, "hanami/src/petals.rs"))
    return {
        "quit_flag": '"--quit"' in main,
        "hidden_flag": '"--hidden"' in main,
        "toggle_flag": '"--toggle"' in main,
        "list_flag": '"--list"' in main,
        "looked_in_log": "looked in {" in main,
        "show_log": 'log("show")' in main,
        "renderer_log": "drawing with" in main,
        # config.rs refuses settings it doesn't know (deny_unknown_fields), and
        # then falls back to all defaults, so only known settings may be written.
        "online_setting": "pub online: bool" in config,
        "petals_setting": "pub petals: u32" in config,
        "default_hotkey": (re.search(r'hotkey: "([^"]+)"\.into\(\)', config) or [None, UNKNOWN])[1],
        "frame_ms": int(frame.group(1)) if frame else UNKNOWN,
        "fixed_petals": int(fixed_petals.group(1)) if fixed_petals else UNKNOWN,
    }


def bench_settings(caps, petals):
    """bench.py flags and the config for one version, and what that changes."""
    flags, notes = [], []
    lines = []
    if caps["online_setting"]:
        lines.append("online = false\n")
    if caps["petals_setting"]:
        lines.append(f"\n[theme]\npetals = {petals}\n")
        petal_count = petals
    else:
        petal_count = caps["fixed_petals"]
        notes.append(f"petals can't be set, it always draws {petal_count}")
    config = "".join(lines)
    if config != bench.config_text(petals):
        flags += ["--config-text", config]
    if not caps["quit_flag"]:
        flags.append("--no-quit")
        notes.append("no --quit, so bench.py stops it with SIGTERM")
    if not caps["online_setting"]:
        notes.append("no online setting (this version has no network code)")
    return flags, petal_count, notes


def unknown_reason(key, caps):
    if key == "hotkey_first_pixel_ms":
        if caps["default_hotkey"] != "Ctrl+Alt+H":
            return f"default hotkey is {caps['default_hotkey']}, not Ctrl+Alt+H"
        return "the panel didn't open on Ctrl+Alt+H sent through XTest"
    if key == "finding_games_per_open_ms":
        if not caps["show_log"]:
            return "no \"show\" line in its --verbose log"
        if not caps["looked_in_log"]:
            return "no \"looked in\" lines in its --verbose log"
        return "no \"looked in\" lines after \"show\" in its --verbose log"
    return "bench.py couldn't measure it"


# Building ------------------------------------------------------------------


def build(ref, commit, builds, jobs, retry):
    """The path of `commit`'s release binary, building it when needed; or (None, reason)."""
    out = builds / "bin" / commit[:12]
    binary, record = out / "hanami", out / "build.json"
    if binary.exists():
        return binary, json.loads(record.read_text()) if record.exists() else {"ok": True}
    if record.exists() and not retry:
        saved = json.loads(record.read_text())
        if not saved.get("ok"):
            return None, saved
    out.mkdir(parents=True, exist_ok=True)
    source = builds / "src" / commit[:12]
    if not source.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        git("worktree", "add", "--detach", str(source), commit)
    env = os.environ | {"CARGO_TARGET_DIR": str(builds / "target")}
    command = ["cargo", "build", "--release", "--locked", "-p", "hanami"] + (["-j", str(jobs)] if jobs else [])
    print(f"Building {ref} ({commit[:12]}) ...", flush=True)
    start = time.perf_counter()
    done = subprocess.run(command, cwd=source, env=env, capture_output=True, text=True)
    seconds = round(time.perf_counter() - start)
    saved = {"ref": ref, "commit": commit, "command": " ".join(command), "seconds": seconds,
             "built_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds")}
    built = builds / "target/release/hanami"
    if done.returncode == 0 and built.exists():
        shutil.copy2(built, binary)
        saved |= {"ok": True, "rustc": bench.run_text("rustc", "--version") or UNKNOWN}
        git("worktree", "remove", "--force", str(source), check=False)
        print(f"  built in {seconds} s", flush=True)
    else:
        errors = [line for line in done.stderr.splitlines() if line.startswith("error")]
        saved |= {"ok": False, "reason": (errors[0] if errors else "cargo failed"),
                  "log_tail": done.stderr.splitlines()[-30:]}
        print(f"  didn't build: {saved['reason']}", flush=True)
    record.write_text(json.dumps(saved, indent=2) + "\n")
    return (binary if saved["ok"] else None), saved


# Measuring -----------------------------------------------------------------


def dig(result, path):
    for part in path:
        if not isinstance(result, dict) or part not in result:
            return None
        result = result[part]
    return result if isinstance(result, (int, float)) else None


def file_name(label):
    return re.sub(r"[^\w.-]", "_", label)


def scrub(text, builds):
    """`text` without this machine's paths or the user's name."""
    text = str(text)
    for path, name in ((builds, "<builds>"), (ROOT, "<repo>"), (Path.home(), "~")):
        text = text.replace(str(path), name)
    text = re.sub(r"/(?:home|tmp|root)(?:/[^\s'\":,)]*)?", "<path>", text)
    user = getpass.getuser()
    return re.sub(rf"\b{re.escape(user)}\b", "<user>", text) if len(user) > 2 else text


PERSONAL = re.compile(r"/(?:home|tmp|root)\b")


def check_private(out_dir, files):
    """Stops if anything written under `out_dir` names a local path or the user."""
    user = getpass.getuser()
    found = []
    for path in files:
        text = path.read_text()
        if PERSONAL.search(text) or (len(user) > 2 and re.search(rf"\b{re.escape(user)}\b", text)):
            found.append(str(path.relative_to(out_dir)))
    if found:
        sys.exit("A local path or the user name got into: " + ", ".join(found))


def run_bench(version, args, round_n, raw, out_dir, builds):
    out = raw / f"{file_name(version['label'])}-round{round_n}.json"
    command = [sys.executable, str(TOOLS / "bench.py"), "--binary", version["binary"],
               "--library", args.library, "--petals", str(args.petals), "--runs", str(args.runs),
               "--sample", str(args.sample), "--out", str(out),
               "--note", f"app_version={version['version']}", "--note", f"commit={version['commit']}",
               "--note", f"petals={version['petals']}",
               # Built from a clean checkout of the commit.
               "--note", "local_changes=false",
               "--note", f"frame_ms={version['capabilities']['frame_ms']}"] + version["bench_flags"]
    env = {key: value for key, value in os.environ.items() if key != "BENCH_IN_DBUS"}
    print(f"Round {round_n}: {version['label']} ...", flush=True)
    start = time.perf_counter()
    try:
        done = subprocess.run(command, env=env, capture_output=True, text=True, timeout=args.timeout)
        ok, tail = done.returncode == 0 and out.exists(), done.stderr.strip().splitlines()[-5:]
    except subprocess.TimeoutExpired:
        ok, tail = False, [f"timed out after {args.timeout} s"]
    tail = [scrub(line, builds) for line in tail]
    run = {"round": round_n, "ok": ok, "seconds": round(time.perf_counter() - start),
           "file": str(out.relative_to(out_dir))}
    if ok:
        run["result"] = json.loads(out.read_text())
    else:
        run["reason"] = tail[-1] if tail else "bench.py failed"
        run["log_tail"] = tail
        print(f"  failed: {run['reason']}", flush=True)
    return run


def collect(version):
    """Median, min and max over rounds per metric; and why any are unknown."""
    metrics, unknown = {}, {}
    for key, path, label, unit in METRICS:
        values = [dig(run["result"], path) for run in version["runs"] if run["ok"]]
        values = [v for v in values if v is not None]
        if values:
            metrics[key] = {"median": round(statistics.median(values), 2), "min": min(values), "max": max(values),
                            "rounds": values, "unit": unit, "label": label}
        elif any(run["ok"] for run in version["runs"]):
            unknown[key] = unknown_reason(key, version["capabilities"])
        else:
            unknown[key] = "no round finished"
    return metrics, unknown


# Writing it up -------------------------------------------------------------


def fmt(metric, ranges=False):
    if metric is None:
        return UNKNOWN
    median = metric["median"]
    text = f"{median:.0f}" if metric["unit"] in ("ms", "") else f"{median:.1f}"
    if ranges and len(metric["rounds"]) > 1:
        lo, hi = metric["min"], metric["max"]
        text += f" ({lo:.0f}-{hi:.0f})" if metric["unit"] in ("ms", "") else f" ({lo:.1f}-{hi:.1f})"
    return text


def markdown(data):
    c = data["conditions"]
    m = c["machine"]
    columns = ["games", "cold_first_pixel_ms", "toggle_first_pixel_ms", "hotkey_first_pixel_ms",
               "cpu_hidden_start", "cpu_open", "cpu_hidden_after", "rss_hidden_start", "rss_hidden_after",
               "pss_hidden_after"]
    labels = {key: (label, unit) for key, _, label, unit in METRICS}
    lines = [
        "# Hanami over versions",
        "",
        f"Measured {c['measured_at']} with tools/bench.py at {c['bench_commit'][:12]}: "
        f"`{c['library']}` library, {c['petals']} petals, {c['rounds']} rounds, {c['runs']} runs per round, "
        f"CPU over {c['sample_seconds']} s.",
        f"{m['cpu_model']}, {m['logical_cores']} logical cores, {m['os']}. {c['display']}.",
        "",
        "Medians over rounds; min and max over rounds are in history.json. "
        "CPU is a percent of one logical core.",
        "",
        "| version | petals | " + " | ".join(f"{labels[k][0]}" + (f" ({labels[k][1]})" if labels[k][1] else "") for k in columns) + " |",
        "|---|---:|" + "---:|" * len(columns),
    ]
    notes = []
    for v in data["versions"]:
        if not v["build"].get("ok"):
            notes.append(f"- {v['label']}: didn't build ({v['build'].get('reason', UNKNOWN)})")
            continue
        if not any(run["ok"] for run in v["runs"]):
            reason = v["runs"][0]["reason"] if v["runs"] else "not measured"
            notes.append(f"- {v['label']}: not measured ({reason})")
            continue
        lines.append(f"| {v['label']} | {v['petals']} | " + " | ".join(fmt(v["metrics"].get(k)) for k in columns) + " |")
        said = v["notes"] + [f"{labels[k][0]} unknown: {why}" for k, why in v["unknown"].items()]
        if said:
            notes.append(f"- {v['label']}: " + "; ".join(said))
    for ref, reason in data.get("not_comparable", {}).items():
        notes.append(f"- {ref}: not comparable ({reason})")
    if notes:
        lines += ["", *notes]
    return "\n".join(lines) + "\n"


def ticks(value):
    """Round axis steps from 0 past `value`: 1, 2 or 5 times a power of ten, at most 5 of them."""
    value = max(value, 1e-9)
    power = 10 ** math.floor(math.log10(value / 5))
    step = next(power * m for m in (1, 2, 5, 10) if value / (power * m) <= 5)
    return [step * n for n in range(math.ceil(value / step - 1e-9) + 1)]


def svg(data):
    """Small multiples, one panel per metric: median as a line and dots, min to max as a whisker."""
    versions = [v for v in data["versions"] if any(run["ok"] for run in v.get("runs", []))]
    width, left, right, top_pad, panel_h = 760, 56, 16, 34, 150
    plot_w = width - left - right
    step = plot_w / max(1, len(versions))
    names = [v["label"].split(" ")[0].removeprefix("v") for v in versions]
    # Names side by side when they fit, slanted when they don't.
    slant = max((len(name) for name in names), default=0) * 6.5 > step - 4
    gap = 58 + (max(len(name) for name in names) * 4.6 if slant and names else 0)
    height = round(len(CHART) * (panel_h + gap) + 30)
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        'font-family="-apple-system, Segoe UI, Helvetica, Arial, sans-serif" font-size="12">',
        "<style>",
        "  .ink { fill: #6e6d68; } .title { fill: #6e6d68; font-weight: 600; font-size: 13px; }",
        "  .grid { stroke: #8a8984; stroke-opacity: 0.25; } .axis { stroke: #8a8984; stroke-opacity: 0.6; }",
        "  .line { stroke: #2a78d6; fill: none; stroke-width: 2; } .dot { fill: #2a78d6; }",
        "  .whisker { stroke: #2a78d6; stroke-opacity: 0.55; stroke-width: 2; }",
        "  @media (prefers-color-scheme: dark) {",
        "    .ink, .title { fill: #c3c2b7; } .line, .whisker { stroke: #3987e5; } .dot { fill: #3987e5; }",
        "  }",
        "</style>",
    ]
    for n, (key, title) in enumerate(CHART):
        y0 = n * (panel_h + gap) + top_pad
        points = [(i, v["metrics"].get(key)) for i, v in enumerate(versions)]
        known = [m for _, m in points if m]
        steps = ticks(max((m["max"] for m in known), default=1))
        top = steps[-1]
        def y(value):
            return y0 + panel_h - panel_h * value / top
        out.append(f'<text class="title" x="{left}" y="{y0 - 14:.0f}">{title}</text>')
        for value in steps:
            out.append(f'<line class="grid" x1="{left}" x2="{width - right}" y1="{y(value):.1f}" y2="{y(value):.1f}"/>')
            label = f"{value:.10g}"
            out.append(f'<text class="ink" x="{left - 8}" y="{y(value) + 4:.1f}" text-anchor="end">{label}</text>')
        out.append(f'<line class="axis" x1="{left}" x2="{width - right}" y1="{y(0):.1f}" y2="{y(0):.1f}"/>')
        path = []
        for i, metric in points:
            x = left + step * (i + 0.5)
            if metric is None:
                path.append(None)
                continue
            path.append((x, y(metric["median"])))
            if metric["max"] > metric["min"]:
                out.append(f'<line class="whisker" x1="{x:.1f}" x2="{x:.1f}" y1="{y(metric["min"]):.1f}" '
                           f'y2="{y(metric["max"]):.1f}"/>')
        segment = []
        for point in path + [None]:
            if point is None:
                if len(segment) > 1:
                    out.append('<polyline class="line" points="' +
                               " ".join(f"{x:.1f},{yy:.1f}" for x, yy in segment) + '"/>')
                segment = []
            else:
                segment.append(point)
        for (i, metric), point in zip(points, path):
            if point is None:
                out.append(f'<text class="ink" x="{left + step * (i + 0.5):.1f}" y="{y(0) - 6:.1f}" '
                           'text-anchor="middle">?</text>')
                continue
            tip = f"{versions[i]['label']}: {fmt(metric, ranges=True)}"
            out.append(f'<circle class="dot" cx="{point[0]:.1f}" cy="{point[1]:.1f}" r="4"><title>{tip}</title></circle>')
        last = next(((i, m) for i, m in reversed(points) if m), None)
        if last:
            i, metric = last
            out.append(f'<text class="ink" x="{left + step * (i + 0.5):.1f}" y="{y(metric["median"]) - 10:.1f}" '
                       f'text-anchor="middle">{fmt(metric)}</text>')
        for i, name in enumerate(names):
            x, ty = left + step * (i + 0.5), y(0) + 16
            if slant:
                out.append(f'<text class="ink" x="{x + 4:.1f}" y="{ty:.1f}" text-anchor="end" font-size="11" '
                           f'transform="rotate(-45 {x + 4:.1f} {ty:.1f})">{name}</text>')
            else:
                out.append(f'<text class="ink" x="{x:.1f}" y="{ty:.1f}" text-anchor="middle" font-size="11">{name}</text>')
    c = data["conditions"]
    out.append(f'<text class="ink" x="{left}" y="{height - 8}" font-size="11">Median of {c["rounds"]} rounds, '
               f'line from min to max. {c["library"]} library, {c["petals"]} petals. ? = unknown.</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def write_reports(data, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "history.json").write_text(json.dumps(data, indent=2) + "\n")
    (out_dir / "history.md").write_text(markdown(data))
    (out_dir / "history.svg").write_text(svg(data))
    check_private(out_dir, [out_dir / name for name in ("history.json", "history.md", "history.svg")])
    print(f"Wrote {out_dir / 'history.json'}, history.md and history.svg")


# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("refs", nargs="*", help="git refs to compare, oldest first (default: every v* tag and HEAD)")
    parser.add_argument("--builds", default=str(Path.home() / ".cache/hanami-compare"),
                        help="where checkouts, the shared build folder and binaries go")
    parser.add_argument("--out-dir", default=str(TOOLS / "results/history"))
    parser.add_argument("--library", choices=sorted(bench.LIBRARIES), default="typical")
    parser.add_argument("--petals", type=int, default=24)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--runs", type=int, default=10, help="bench.py --runs")
    parser.add_argument("--sample", type=float, default=10, help="bench.py --sample, seconds to measure CPU over")
    parser.add_argument("--timeout", type=int, default=900, help="seconds before one bench.py run counts as failed")
    parser.add_argument("--jobs", type=int, help="cargo -j")
    parser.add_argument("--retry", action="store_true", help="try again to build refs that didn't build before")
    parser.add_argument("--build-only", action="store_true", help="build, don't measure")
    parser.add_argument("--report", metavar="JSON", help="only redraw history.md and history.svg from a saved history.json")
    args = parser.parse_args()

    if args.report:
        data = json.loads(Path(args.report).read_text())
        write_reports(data, Path(args.out_dir) if args.out_dir != str(TOOLS / "results/history") else Path(args.report).parent)
        return

    builds = Path(args.builds).expanduser().resolve()
    builds.mkdir(parents=True, exist_ok=True)
    versions = []
    for ref in args.refs or default_refs():
        commit = git("rev-parse", f"{ref}^{{commit}}", check=False)
        if not commit:
            print(f"{ref}: no such ref, skipped")
            continue
        number = re.search(r'^version = "(.*)"', show(commit, "hanami/Cargo.toml"), re.MULTILINE)
        number = number.group(1) if number else UNKNOWN
        label = ref if ref.startswith("v") else f"{ref} ({number}, {commit[:7]})"
        caps = capabilities(commit)
        flags, petals, notes = bench_settings(caps, args.petals)
        binary, record = build(ref, commit, builds, args.jobs, args.retry)
        # The cargo log stays in the build cache; what's shared has no local paths.
        record = {key: scrub(value, builds) if isinstance(value, str) else value
                  for key, value in record.items() if key != "log_tail"}
        versions.append({"ref": ref, "label": label, "commit": commit, "version": number,
                         "binary": str(binary) if binary else None, "build_id": commit[:12], "build": record,
                         "capabilities": caps,
                         "bench_flags": flags, "petals": petals, "notes": notes, "runs": []})

    print("\nBuilds:")
    for v in versions:
        print(f"  {v['label']:<28} {'ok' if v['build'].get('ok') else 'did not build: ' + v['build'].get('reason', '')}")
    if args.build_only:
        return

    built = [v for v in versions if v["binary"]]
    for v in built:
        if not (v["capabilities"]["hidden_flag"] and v["capabilities"]["toggle_flag"] and v["capabilities"]["list_flag"]):
            v["skip"] = "needs --hidden, --toggle and --list"
            v["runs"].append({"round": 0, "ok": False, "reason": v["skip"]})
    measured = [v for v in built if "skip" not in v]
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.out_dir).resolve()
    raw = out_dir / "raw" / stamp
    raw.mkdir(parents=True, exist_ok=True)
    started = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    orders = []
    for round_n in range(1, args.rounds + 1):
        order = measured if round_n % 2 else list(reversed(measured))
        orders.append([v["label"] for v in order])
        for v in order:
            v["runs"].append(run_bench(v, args, round_n, raw, out_dir, builds))
    for v in versions:
        v["metrics"], v["unknown"] = collect(v) if v["runs"] else ({}, {})

    first = next((run["result"]["conditions"] for v in measured for run in v["runs"] if run["ok"]), {})
    data = {
        "conditions": {
            "measured_at": started,
            "finished_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            "bench_commit": git("rev-parse", "HEAD"),
            "bench_local_changes": bool(git("status", "--porcelain", check=False)),
            "machine": bench.machine(),
            "display": first.get("display", {}).get("server", UNKNOWN),
            "library": args.library,
            "library_counts": first.get("library", {}).get("counts", UNKNOWN),
            "petals": args.petals,
            "rounds": args.rounds,
            "runs": args.runs,
            "sample_seconds": args.sample,
            "round_orders": orders,
            "how": "each version built in release mode from its own checkout; tools/bench.py from bench_commit "
                   "run against each with the same settings; versions interleaved, every other round reversed; "
                   "per metric the median over rounds, with min and max",
            "raw_results": str(raw.relative_to(out_dir)),
        },
        "versions": [{key: value for key, value in v.items() if key != "binary"} for v in versions],
    }
    write_reports(data, out_dir)
    check_private(out_dir, sorted(raw.glob("*.json")))


if __name__ == "__main__":
    main()
