# Hanami over versions

Measured 2026-10-24T17:44:28+00:00 with tools/bench.py at bc9144705a91: `typical` library, 24 petals, 3 rounds, 10 runs per round, CPU over 10 s.
Intel(R) Xeon(R) Processor, 4 logical cores, Ubuntu 24.04.5 LTS, Linux 6.18.44-fc-v153. Xvfb 1920x1080x24, no window manager, no compositor.

Medians over rounds; min and max over rounds are in history.json. CPU is a percent of one logical core.

| version | petals | games listed | cold start to first pixel (ms) | --toggle to first pixel (ms) | Ctrl+Alt+H to first pixel (ms) | CPU hidden at start (%) | CPU open (%) | CPU hidden after opening (%) | RSS hidden at start (MB) | RSS hidden after opening (MB) | PSS hidden after opening (MB) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| v0.1.0 | 18 | 200 | 35 | 9 | 11 | 0.1 | 3.9 | 0.1 | 20.6 | 25.7 | 22.4 |
| v0.1.1 | 18 | 200 | 35 | 9 | 11 | 0.1 | 3.7 | 0.2 | 20.6 | 25.9 | 22.6 |
| v0.1.2 | 18 | 200 | 35 | 9 | 11 | 0.2 | 4.3 | 0.1 | 20.7 | 25.9 | 22.7 |
| v0.2.0 | 18 | 200 | 37 | 12 | 11 | 0.2 | 6.3 | 0.3 | 23.6 | 32.6 | 29.3 |
| v0.2.1 | 18 | 200 | 38 | 12 | 16 | 0.2 | 6.4 | 0.2 | 23.3 | 30.7 | 27.4 |
| v0.2.2 | 18 | 200 | 38 | 12 | 11 | 0.2 | 6.5 | 0.2 | 23.3 | 31.0 | 27.6 |
| v0.2.3 | 18 | 200 | 39 | 12 | 12 | 0.3 | 6.3 | 0.3 | 23.3 | 30.9 | 27.6 |
| v0.2.4 | 18 | 200 | 40 | 12 | 17 | 0.3 | 6.2 | 0.3 | 23.2 | 30.5 | 27.2 |
| v0.2.5 | 18 | 200 | 39 | 12 | 13 | 0.2 | 6.4 | 0.2 | 23.4 | 30.7 | 27.4 |
| v0.2.6 | 18 | 200 | 39 | 12 | 14 | 0.2 | 6.4 | 0.2 | 23.5 | 31.0 | 27.7 |
| v0.2.7 | 18 | 200 | 40 | 12 | 12 | 0.2 | 6.6 | 0.3 | 23.1 | 30.6 | 27.3 |
| v0.2.8 | 24 | 200 | 39 | 13 | 56 | 0.2 | 7.1 | 0.2 | 23.2 | 31.2 | 27.9 |
| v0.2.9 | 24 | 200 | 40 | 14 | 58 | 0.2 | 7.1 | 0.2 | 23.6 | 31.7 | 28.4 |
| v0.2.10 | 24 | 200 | 44 | 13 | 59 | 0.2 | 7.0 | 0.3 | 23.3 | 31.3 | 28.0 |
| v0.2.11 | 24 | 200 | 40 | 13 | 57 | 0.3 | 7.2 | 0.3 | 23.4 | 31.5 | 28.2 |
| v0.2.12 | 24 | 200 | 40 | 14 | 53 | 0.1 | 7.0 | 0.2 | 23.5 | 31.4 | 28.0 |
| v0.2.13 | 24 | 200 | 41 | 14 | 39 | 0.2 | 6.9 | 0.2 | 23.3 | 31.5 | 28.1 |
| 0.2.14-pre (main at bd8ee9b, before smaller icons and skipped empty frames) | 24 | 200 | 38 | 6 | 4 | 0.0 | 2.9 | 0.0 | 24.8 | 29.1 | 25.9 |
| 0.2.14 (with smaller icons and skipped empty frames) | 24 | 200 | 39 | 6 | 4 | 0.0 | 2.8 | 0.0 | 25.2 | 28.1 | 24.9 |

- v0.1.0: petals can't be set, it always draws 18; no --quit, so bench.py stops it with SIGTERM; no online setting (this version has no network code)
- v0.1.1: petals can't be set, it always draws 18; no --quit, so bench.py stops it with SIGTERM; no online setting (this version has no network code)
- v0.1.2: petals can't be set, it always draws 18; no --quit, so bench.py stops it with SIGTERM; no online setting (this version has no network code)
- v0.2.0: petals can't be set, it always draws 18; no --quit, so bench.py stops it with SIGTERM
- v0.2.1: petals can't be set, it always draws 18; no --quit, so bench.py stops it with SIGTERM
- v0.2.2: petals can't be set, it always draws 18
- v0.2.3: petals can't be set, it always draws 18
- v0.2.4: petals can't be set, it always draws 18
- v0.2.5: petals can't be set, it always draws 18
- v0.2.6: petals can't be set, it always draws 18
- v0.2.7: petals can't be set, it always draws 18
