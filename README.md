<div align="center">

<picture>
  <source media="(prefers-color-scheme: light)" srcset="docs/images/banner-light.svg">
  <img alt="Hanami, a small game launcher for Linux and Windows, with falling sakura petals" src="docs/images/banner-dark.svg" width="100%">
</picture>

<br><br>

[![Latest release](https://img.shields.io/github/v/release/sjdsjadjajdjsa/hanami?color=f4b6c8&labelColor=17141d&label=release)](https://github.com/sjdsjadjajdjsa/hanami/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/sjdsjadjajdjsa/hanami/total?color=f4b6c8&labelColor=17141d)](https://github.com/sjdsjadjajdjsa/hanami/releases)
[![CI](https://img.shields.io/github/actions/workflow/status/sjdsjadjajdjsa/hanami/ci.yml?branch=main&label=ci&labelColor=17141d)](https://github.com/sjdsjadjajdjsa/hanami/actions/workflows/ci.yml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-9b93a3?labelColor=17141d)](LICENSE)
[![Linux and Windows](https://img.shields.io/badge/platform-Linux%20%7C%20Windows-9b93a3?labelColor=17141d)](#install)

**[Download](https://github.com/sjdsjadjajdjsa/hanami/releases/latest)** ·
[Website](https://hanami.lilygrove.dev) ·
[Guide](GUIDE.md) ·
[Any AI](#any-harness-any-model) ·
[Performance](#performance) ·
[Report a problem](https://github.com/sjdsjadjajdjsa/hanami/issues/new/choose)

<picture>
  <source media="(prefers-color-scheme: light)" srcset="docs/demo-light.webp">
  <img src="docs/demo-dark.webp" width="800" alt="The Hanami panel opens, typing hk finds Hollow Knight, and Tab pins a game to the top, with sakura petals falling over a dark, see-through window">
</picture>

</div>

Hanami lives in the system tray. `Ctrl+Alt+H`, the tray icon or Start and
Select on a controller opens the panel. Type a few letters, press Enter, play.

## Features

<picture>
  <source media="(prefers-color-scheme: light)" srcset="docs/images/features-light.svg">
  <img alt="Every launcher in one list, forgiving search, pins and renames, ports and rewrites, Minecraft instances, controller support, custom colours and petals, a tiny footprint, AI help and crash reports" src="docs/images/features-dark.svg" width="100%">
</picture>

<details>
<summary>More about each feature</summary>

- **Search that forgives:** first letters and small typos work, so `hk`
  finds Hollow Knight. Enter launches; Tab or right-click shows more.
- **Your list:** pin games to the top, rename or hide them, add any program
  with **+**. The games you played last come first.
- **Ports and rewrites:** finds Ship of Harkinian, Zelda 64: Recompiled,
  OpenMW and more, and, if you want, Rust games you built yourself. New
  finds wait for a yes before they join the list.
- **Minecraft:** one row that opens to your instances; the launcher starts
  them and handles the Microsoft login.
- **Your look:** colours and the falling petals are two small files. Write
  them yourself or ask your AI for "autumn, with maple leaves"
  ([how](GUIDE.md#changing-the-look)).
- **Light:** about 28 MB of memory with 200 games, and under 3 % of one core
  while the panel is open.
- **Problems:** **Report a problem** in the tray menu opens a filled-in
  GitHub issue, with what went wrong if Hanami crashed. Nothing is sent
  until you press Submit.
- **AI help:** the **?** button copies a prompt with the full documentation,
  for assistants that can read your computer (Claude Code, OpenCode and
  similar).

</details>

## Finds your games

<picture>
  <source media="(prefers-color-scheme: light)" srcset="docs/images/sources-light.svg">
  <img alt="Steam and Heroic on Linux and Windows, Epic and GOG on Windows, Lutris and the app menu on Linux, ports and rewrites, Minecraft through Prism, PolyMC or MultiMC, and any program you add" src="docs/images/sources-dark.svg" width="100%">
</picture>

Known ports and rewrites are listed in [ports.toml](ports.toml).

## Any harness, any model

Six AI coding agents, each on a different model, each change one thing
about the same Hanami. Hanami's guide is written for agents to read, so any
of them gets it right.

<picture>
  <source media="(prefers-color-scheme: light)" srcset="docs/images/agents-light.svg">
  <img alt="Crush hides Dead Cells, OpenCode renames Stardew Valley, Antigravity CLI pins two games, jcode makes it autumn, Codex sets Ctrl+Space, Claude Code finds Minecraft" src="docs/images/agents-dark.svg" width="100%">
</picture>

The agents and models ran for real; the video is on [the website](https://hanami.lilygrove.dev).

### Your look, from one sentence

<picture>
  <source media="(prefers-color-scheme: light)" srcset="docs/images/looks-light.webp">
  <img alt="The real panel three times: sakura by default, autumn with maple leaves, and snow, each written by an AI from one sentence" src="docs/images/looks-dark.webp" width="100%">
</picture>

Colours and the falling shape are two small files an AI can write
([how](GUIDE.md#changing-the-look)).

## Performance

<picture>
  <source media="(prefers-color-scheme: light)" srcset="docs/images/stats-light.svg">
  <img alt="28 MB of memory with 200 games, 2.8 % of one core with the panel open, 6 ms from hotkey to panel" src="docs/images/stats-dark.svg" width="100%">
</picture>

![CPU while open, memory and time to open, for every release](tools/results/history/history.svg)

With 200 games, 0.2.14 uses under 3 % of one core with the panel open and
28 MB of memory, and opens in 6 ms. [docs/benchmarks.md](docs/benchmarks.md)
has every release, how it was measured, and how to run it yourself.

## Install

<a href="https://github.com/sjdsjadjajdjsa/hanami/releases/latest">
<picture>
  <source media="(prefers-color-scheme: light)" srcset="docs/images/install-light.svg">
  <img alt="Linux: hanami-x86_64.AppImage. Windows: hanami-setup-x86_64.exe. Portable tar.gz and zip. Or cargo build --release" src="docs/images/install-dark.svg" width="100%">
</picture>
</a>

<details>
<summary>Every download, and checking it</summary>

| | Download | Notes |
|---|---|---|
| **Linux** | `hanami-x86_64.AppImage` | Mark it executable (right-click, Properties, or `chmod +x`) and run it. Needs a distribution from 2022 or newer (Ubuntu 22.04, Fedora 36, Mint 21, Debian 12, Arch, and so on). |
| **Windows** | `hanami-setup-x86_64.exe` | Installs for your user only, with no admin rights. Adds a Start menu entry and, if you tick the box, starts Hanami with Windows. |

Windows will say the publisher is unknown, as the installer isn't signed:
click "More info", then "Run anyway". If you don't want an installer, there
are also `hanami-linux-x86_64.tar.gz` and `hanami-windows-x86_64.zip` with
the plain program.

Each release also has a `SHA256SUMS` file and a signed record of how every
file was built; [SECURITY.md](SECURITY.md) says how to check a download and
how to report a security problem.

Hanami says in its tray menu when a newer version is out; it never updates
itself. To start it with your computer, pick **Open at login** in the tray
menu.

</details>

## Use

- **Open and close:** `Ctrl+Alt+H`, a click on the tray icon, or
  `hanami --toggle`.
- **Move it:** on Windows, hold Alt or the Windows key and drag; on Linux,
  your desktop's own key for moving windows does it.
- **Pick a game:** type to search, arrows and Enter, or click.
- **More for one game:** Tab or right-click: Pin to top, Rename, Hide.
- **Add a game:** the **+** button.
- **Settings:** tray icon, Edit settings. Everything they can hold is in
  [GUIDE.md](GUIDE.md).

## Build from source

Needs [Rust](https://rustup.rs). On Linux, also the development packages
for xkbcommon, fontconfig, Wayland, D-Bus and udev (on Debian and Ubuntu:
`libxkbcommon-dev libfontconfig1-dev libwayland-dev libdbus-1-dev libudev-dev`).

```
cargo build --release
./target/release/hanami
```

More in [docs/](docs): [SPEC.md](docs/SPEC.md) says what Hanami does,
[DESIGN.md](docs/DESIGN.md) how it looks, [ROADMAP.md](docs/ROADMAP.md) what
comes next, and [PORTS.md](docs/PORTS.md) how to add a port. To help out, see
[CONTRIBUTING.md](CONTRIBUTING.md). The website is in [site/](site). The
README cards are drawn by `docs/banner.py` and `docs/cards.py` (they need
`fonttools`), the three looks by `docs/looks.py`, the screenshots and short videos by the scripts in
[docs/video](docs/video/README.md).

## License

Hanami is free software under the [GNU GPL, version 3 or later](LICENSE).
It is built with [Slint](https://slint.dev) and ships the
[Inter](https://rsms.me/inter/) typeface (SIL Open Font License, in
`assets/Inter-LICENSE.txt`). The maple leaf and snowflake examples in the
guide are from Microsoft's
[Fluent Emoji](https://github.com/microsoft/fluentui-emoji) (MIT).
