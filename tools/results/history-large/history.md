# Hanami over versions

Measured 2026-10-24T18:36:33+00:00 with tools/bench.py at 0efff76a8592: `large` library, 24 petals, 3 rounds, 10 runs per round, CPU over 10 s.
Intel(R) Xeon(R) Processor, 4 logical cores, Ubuntu 24.04.5 LTS, Linux 6.18.44-fc-v153. Xvfb 1920x1080x24, no window manager, no compositor.

Medians over rounds; min and max over rounds are in history.json. CPU is a percent of one logical core.

| version | petals | games listed | cold start to first pixel (ms) | --toggle to first pixel (ms) | Ctrl+Alt+H to first pixel (ms) | CPU hidden at start (%) | CPU open (%) | CPU hidden after opening (%) | RSS hidden at start (MB) | RSS hidden after opening (MB) | PSS hidden after opening (MB) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.2.14-pre (main at bd8ee9b, before smaller icons and skipped empty frames) | 24 | 1350 | 59 | 10 | 8 | 0.0 | 3.0 | 0.0 | 25.5 | 35.2 | 32.0 |
| 0.2.14 (with smaller icons and skipped empty frames) | 24 | 1350 | 59 | 10 | 7 | 0.0 | 2.9 | 0.0 | 25.8 | 31.7 | 28.4 |
