# Hanami

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: light)" srcset="docs/screenshot-light.webp">
    <img src="docs/screenshot-dark.webp" width="800" alt="The Hanami panel: a dark, see-through rounded window listing games, with sakura petals falling behind it and around it">
  </picture>
</p>

A game launcher for Linux and Windows. It runs in the system tray and
opens a small panel that lists your installed games.

- **Game detection:** Steam, Heroic (Epic, GOG, Amazon), Lutris and desktop
  entries on Linux; Steam, Epic, GOG and Heroic on Windows. Each game shows
  its own icon.
- **Ports and rewrites:** finds known ports, recomps and rewrites (Ship of
  Harkinian, Zelda 64: Recompiled, OpenMW and more, listed in
  [ports.toml](ports.toml)) and, if you want, Rust games you built yourself.
  New finds wait for a yes before they join the list.
- **Your list:** pin games to the top, rename or hide them, add any program
  with **+**. Games you played last come first.
- **Controls:** `Ctrl+Alt+H` or the tray icon opens the panel; type to
  search (first letters and small typos work too), Enter to launch, Tab or
  right-click for more. A game controller works too: hold Start and Select.
- **Resource use:** about 35 MB of memory, no CPU use while hidden.
- **AI help prompt:** the **?** button copies a prompt containing the full
  documentation, for AI assistants that can read your computer (Claude Code,
  OpenCode and similar) to answer questions about Hanami.

Website: <https://hanami.lilygrove.dev>

## Install

Download the newest version from
[Releases](https://github.com/sjdsjadjajdjsa/hanami/releases/latest):

- **Linux:** `hanami-x86_64.AppImage`. Mark it executable and run it. There
  is also `hanami-linux-x86_64.tar.gz` with the plain binary.
- **Windows:** `hanami-setup-x86_64.exe`. It installs for your user only (no
  admin rights), adds a Start menu entry and can start Hanami with Windows.
  `hanami-windows-x86_64.zip` is the same program without an installer.

Each release also has a `SHA256SUMS` file and a signed record of how every
file was built; [SECURITY.md](SECURITY.md) says how to check a download and
how to report a security problem.

Hanami says in its tray menu when a newer version is out; it never updates
itself. To start it with your computer on Linux, add `hanami --hidden` to
your startup programs ([how](GUIDE.md#starting-with-the-computer)).

## Use

- **Open and close:** `Ctrl+Alt+H`, a click on the tray icon, or
  `hanami --toggle` (bind that to a key on Wayland).
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

[SPEC.md](SPEC.md) says what Hanami does, [DESIGN.md](DESIGN.md) how it
looks, and [ROADMAP.md](ROADMAP.md) what comes next. The website is in
[site/](site); `hanami --snapshot panel.png` and then
`python3 docs/screenshot.py panel.png` redraw the README pictures.

## License

Hanami is free software under the [GNU GPL, version 3 or later](LICENSE).
It is built with [Slint](https://slint.dev) and ships the
[Inter](https://rsms.me/inter/) typeface (SIL Open Font License, in
`assets/Inter-LICENSE.txt`).
