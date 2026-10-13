# Hanami

<p align="center"><img src="docs/screenshot.png" width="420" alt="The Hanami panel: a dark, rounded window listing games, with sakura petals behind the list"></p>

A small game launcher for Linux and Windows. It lives in the tray, opens as
a rounded, see-through panel with sakura petals drifting behind your games,
starts the one you pick, and gets out of the way.

- **Finds your games by itself:** Steam, Heroic (Epic, GOG, Amazon), Lutris
  and the games in your Linux app menu; Steam, Epic and GOG on Windows. Add
  anything else in one settings file.
- **Light:** written in Rust, about 30 MB of memory and no CPU while hidden.
- **Quick:** `Ctrl+Alt+H` or a click on the tray icon, type a few letters,
  press Enter.
- **Explains itself:** the **?** button copies a prompt you can paste into
  any AI that can see your computer (Claude Code, Kimi Code, OpenCode, ...),
  and it walks you through everything Hanami can do.

## Install

Download the newest version from
[Releases](https://github.com/sjdsjadjajdjsa/hanami/releases):

- **Linux:** `hanami-linux-x86_64.tar.gz`. Unpack it and run `hanami`.
- **Windows:** `hanami-windows-x86_64.zip`. Unpack it and run `hanami.exe`.

To have it in the tray from the start, add `hanami --hidden` to the programs
that start with your computer ([how](GUIDE.md#starting-with-the-computer)).

## Use

- **Open and close:** `Ctrl+Alt+H`, a click on the tray icon, or
  `hanami --toggle` (bind that to a key on Wayland).
- **Pick a game:** type to search, arrows and Enter, or click.
- **Settings:** tray icon, Edit settings. Everything they can hold is in
  [GUIDE.md](GUIDE.md).

## Build from source

Needs [Rust](https://rustup.rs). On Linux, also the development packages
for xkbcommon, fontconfig, Wayland and D-Bus (on Debian and Ubuntu:
`libxkbcommon-dev libfontconfig1-dev libwayland-dev libdbus-1-dev`).

```
cargo build --release
./target/release/hanami
```

[SPEC.md](SPEC.md) says what Hanami does, [DESIGN.md](DESIGN.md) how it
looks, and [ROADMAP.md](ROADMAP.md) what comes next. The website is in
[site/](site), and `hanami --snapshot picture.png` redraws the screenshots.

## License

Hanami is free software under the [GNU GPL, version 3 or later](LICENSE).
It is built with [Slint](https://slint.dev) and ships the
[Inter](https://rsms.me/inter/) typeface (SIL Open Font License, in
`assets/Inter-LICENSE.txt`).
