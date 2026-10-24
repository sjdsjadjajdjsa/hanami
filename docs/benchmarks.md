# Benchmarks

How much Hanami costs your computer, release by release, measured the same
way each time.

![CPU while open, memory hidden after opening, and time to open, for every release](../tools/results/history/history.svg)

## What changed when

- **0.1.0 to 0.1.2:** about 4 % of one core with the panel open, 26 MB.
  18 petals and no icons.
- **0.2.0:** icons, pin, rename and hide, ports, the controller and the
  update check came in. Open CPU went to about 6 %, memory to about 31 MB.
- **0.2.8:** 24 petals instead of 18, and the look became a setting. About
  7 % open.
- **Up to 0.2.13**, the hotkey library on X11 looked for key presses every
  50 ms, so Ctrl+Alt+H took anywhere from a few ms to about 60 ms, depending
  on when the key landed. The benchmark presses it in a fixed rhythm, which
  happened to land early in some versions (about 11 ms) and late in others
  (about 55 ms); those differences aren't real changes.
- **0.2.14:** only the rows you can see are built, so the open panel is
  under 3 %. The panel shows the games found last and looks for new ones
  after it is up, so opening with `hanami --toggle` takes 6 ms instead of
  14. The hotkey waits for the key instead of looking for it, so Ctrl+Alt+H
  shows the panel in 4 ms. Icons are kept at the size they are drawn (24 px
  on a normal screen, not 48), which takes about 1 MB off with 200 games and
  3.5 MB with 1,350. An empty frame Slint drew after each petal step is
  skipped: about 7 % fewer instructions per frame, too small to see in the
  CPU numbers on this machine.

## The numbers

200 games (`--library typical`), 24 petals (18 before 0.2.8, which can't be
changed), medians of 3 rounds. CPU is a percent of one logical core.

| Version | Open CPU | Memory hidden after opening (RSS) | `--toggle` to first pixel | Ctrl+Alt+H to first pixel | Cold start to first pixel |
|---|---:|---:|---:|---:|---:|
| 0.1.0 | 3.9 % | 25.7 MB | 9 ms | 11 ms | 35 ms |
| 0.1.2 | 4.3 % | 25.9 MB | 9 ms | 11 ms | 35 ms |
| 0.2.0 | 6.3 % | 32.6 MB | 12 ms | 11 ms | 37 ms |
| 0.2.7 | 6.6 % | 30.6 MB | 12 ms | 12 ms | 40 ms |
| 0.2.8 | 7.1 % | 31.2 MB | 13 ms | 56 ms | 39 ms |
| 0.2.13 | 6.9 % | 31.5 MB | 14 ms | 39 ms | 41 ms |
| 0.2.14 | 2.8 % | 28.1 MB | 6 ms | 4 ms | 39 ms |

Every release, with the range of each number and how each version was
started, is in [history.md](../tools/results/history/history.md); the raw
runs are next to it. With 1,350 games, 0.2.14 uses 31.7 MB hidden after
opening instead of 35.2 MB
([history-large](../tools/results/history-large/history.md)).

While hidden, every version reads 0.0 to 0.3 % here, as low as this way of
measuring can go. What still wakes Hanami up while hidden is in
[ROADMAP.md](../ROADMAP.md#measured).

## How this was measured

- On a shared cloud machine: 4 logical cores (Intel Xeon), 16 GB, no GPU,
  Ubuntu 24.04, a virtual screen (Xvfb, 1920x1080, scale 1) with no window
  manager, compositor or blur. Hanami draws with the CPU, as it does on a
  normal Linux desktop.
- Every release was built from its tag and run against the same made-up
  library from `tools/bench.py`, in turns (all versions, then all in reverse,
  then all again), so a slow moment on the machine doesn't land on one
  version.
- This machine's CPU readings move by about a point from run to run.
  Differences smaller than that, like 2.9 against 2.8 %, aren't real
  differences.
- These numbers compare versions with each other. They aren't the targets
  in SPEC.md, which are measured on a real desktop; that run is still to
  come.

## Run it yourself

```
cargo build --release
python3 tools/bench.py --library typical
python3 tools/compare.py --rounds 3
```

`tools/bench.py` measures the version you built; `tools/compare.py` builds
every release (about 10 minutes the first time, 3.5 GB of build files) and
compares them. Both need Linux, Xvfb and `dbus-run-session`, and neither
touches your own settings or games: they work in a temporary folder.
