# Hanami guide

Hanami is a game launcher for Linux and Windows
(<https://github.com/sjdsjadjajdjsa/hanami>, free software under the GPL).
It runs in the system tray and opens a small panel that lists the installed
games. Picking a game starts it and hides the panel.

## Opening and closing

- **Hotkey:** `Ctrl+Alt+H` by default. Press it again to close.
- **Tray icon:** click to open or close. Right-click for Open, Edit
  settings, Quit.
- **Command:** `hanami --toggle` opens or closes it. On Wayland, apps can't
  grab keys themselves, so bind this command to a key in the desktop's own
  keyboard shortcut settings.
- **Closing:** Esc, clicking somewhere else, the hotkey, or the tray icon.
- Only one Hanami runs at a time; starting it again opens the running one.

## In the panel

- Type to search. Arrow keys move, Enter or a click starts the game.
- Each game has a small label saying where it came from: steam, epic, gog,
  amazon, lutris, heroic, app, port, rust, or your own label.
- Problems (a typo in the settings, a game that won't start) show as one
  line at the bottom for a few seconds.
- The **?** button copies a prompt with this guide, for an AI assistant.

## Where games come from

Hanami finds installed games by itself, every time the panel opens:

| Name in settings | What it finds | Systems |
|---|---|---|
| `steam` | installed Steam games, without Proton and runtimes | Linux, Windows |
| `heroic` | Heroic's Epic, GOG and Amazon games and programs added to Heroic (native and Flatpak) | Linux, Windows |
| `lutris` | installed Lutris games, except those in Lutris's hidden category | Linux |
| `apps` | games in the app menu (desktop entries in the Game category that aren't also Utility); Steam, Heroic and Lutris themselves are left out because their games are found directly | Linux |
| `epic` | Epic Games Launcher games (not DLC or engine tools) | Windows |
| `gog` | GOG Galaxy and GOG installer games | Windows |
| `ports` | game ports, recomps and rewrites (see below), games that come with a `hanami-game.toml`, and your own built Rust games from the `projects` folders | Linux, Windows |

The same game found twice (for example in Steam and in the app menu) is
listed once. Games added in the settings file win over found ones.

### Ports, recomps and rewrites

Hanami knows a list of PC ports of console games and rewrites of old games
(Ship of Harkinian, 2 Ship 2 Harkinian, Starship, SpaghettiKart, Ghostship,
Zelda 64: Recompiled, sm64coopdx, Perfect Dark, OpenMW, OpenRCT2, OpenTTD,
DevilutionX, fheroes2, Augustus, Julius, CorsixTH, GZDoom, UZDoom, Ironwail,
vkQuake, the Sonic decompilations and Sonic 3 A.I.R.). The list is
`ports.toml` in Hanami's repository; PORTS.md says how to add one. Hanami
ships a copy and, when `online = true`, fetches the newest copy from GitHub
once a day into its cache folder (`~/.cache/hanami/ports.toml` on Linux,
`%LOCALAPPDATA%\hanami\ports.toml` on Windows); the higher `version` wins.

It looks for the ports' program files, by name, in:

- the `folders` setting
- Linux: `~/Games`, `~/Applications`, `~/AppImages`, `/opt`, and `~/Downloads`
  (only one folder deep)
- Windows: `~/Games`, `C:\Games`, `D:\Games`, the Desktop and Downloads
  (two folders deep)
- Flatpaks in `~/.local/share/flatpak/app` and `/var/lib/flatpak/app`,
  started with `flatpak run`

On Linux the file must be executable (`chmod +x soh.appimage`). Hidden
folders, `node_modules`, `target`, `vendor`, Wine and Proton prefixes and
Steam libraries are skipped, and folders are searched at most four levels
down. These games get the label `port`.

A game that ships a `hanami-game.toml` next to its program is found in the
same places (PORTS.md describes the file). Its label is `port` unless the
file says otherwise.

### Your own Rust games

With `projects = ["~/Projects"]`, Hanami looks at every folder (and
sub-folder, one level down) with a `Cargo.toml` in it. A package counts as
a game when it depends on a game engine or framework (bevy, fyrox,
macroquad, miniquad, ggez, tetra, notan, comfy, raylib, sdl2, sdl3, three-d,
kiss3d, piston, speedy2d, godot and a few more, also through
`[workspace.dependencies]`), or when it has a `[package.metadata.hanami]`
table. Workspaces are followed through `members`.

Only built games are offered: the package's program must exist in
`target/release` (preferred) or `target/debug` (`.cargo/config.toml`
`target-dir` is respected). The program is `default-run` if set, else the
one named like the package, else the only one; several programs without a
default are all offered. A `play.sh` (Linux) or `play.bat` (Windows) next
to the project's `Cargo.toml` is started instead of the program when there
is one. Games run from the project's root folder, like `cargo run`.

The name comes from `[package.metadata.hanami] name`, else from the package
name made readable: `skate-game` is `Skate Game`, `pixel-gun-3d-rs` is
`Pixel Gun 3D`. The metadata table can also hold `args = [...]` and
`icon = "path/relative/to/Cargo.toml"`. Label: `rust`. Folders named
`backup` (or containing it), `target`, `vendor`, `node_modules` and hidden
folders are skipped.

The `ports` search runs in the background: the panel shows the last result
at once and a new search starts when that result is about a minute old, so
a freshly downloaded port can take a minute (or two panel opens) to show.
`hanami --list` searches right away.

## Settings

One file, created with comments the first time Hanami runs:

- Linux: `~/.config/hanami/config.toml` (or `$XDG_CONFIG_HOME/hanami/config.toml`)
- Windows: `%APPDATA%\hanami\config.toml`

Changes show up the next time the panel opens; only `hotkey` needs a
restart. A mistake in the file is reported in the panel and the last good
settings stay in use. Everything it can hold:

```toml
# Key that opens and closes the panel. Modifiers: Ctrl, Alt, Shift, Super.
hotkey = "Ctrl+Alt+H"

# After a game starts: "hide" the panel, "keep" it open, or "quit" Hanami.
on_launch = "hide"

# Where to look for installed games (see the table above).
find = ["steam", "heroic", "lutris", "apps", "epic", "gog", "ports"]

# Found games to leave out, by name (case and punctuation don't matter).
hide = ["Some Game"]

# Extra folders to search for ports and games with a hanami-game.toml.
folders = ["~/Emulation/ports"]

# Folders with your own Rust game projects; built games are offered.
projects = ["~/Projects"]

# Fetch the newest ports list from GitHub once a day. false = never go online.
online = true

# Your own games. Any program can be a game. ~ means the home folder.
[[game]]
name = "My Game"
command = "~/Games/my-game/my-game"   # the program to run
args = ["--fullscreen"]               # optional
dir = "~/Games/my-game"               # optional: folder it runs in
label = "my label"                    # optional: the label shown in the list
```

Games started by Hanami keep running when Hanami closes.

## Commands

| Command | What it does |
|---|---|
| `hanami` | open the panel (starts Hanami if needed) |
| `hanami --hidden` | start in the tray only; use this to start with the computer |
| `hanami --toggle` | open or close the panel |
| `hanami --list` | print every game the panel would show, with its label |
| `hanami --guide` | print the AI prompt the **?** button copies |
| `hanami --verbose` | print what happens (opening, focus, where games were found, how long the ports search took) for bug reports |
| `hanami --snapshot picture.png` | draw the panel with sample games into a picture, without opening it |

## Starting with the computer

- KDE Plasma: System Settings, Autostart, Add Application, then pick Hanami
  and change its command to `hanami --hidden`.
- GNOME and others: add a startup entry that runs `hanami --hidden`.
- Windows: put a shortcut to `hanami.exe --hidden` in the Startup folder
  (`shell:startup` in the Run box).

## Changing the look

There is no theme setting yet. The look is built from a small set of colours,
sizes and spacing kept in one place, so changing it means editing the source:

- `hanami/ui/hanami.slint`, the `Tokens` block at the top: panel colour and
  see-through amount, text colours, the pink highlight, sizes, spacing and
  corner rounding.
- The petals: count, speed and size in `petals()` in `hanami/src/main.rs`;
  their shape in `assets/petal.svg`.
- `DESIGN.md` explains the rules behind the look.

Then rebuild with `cargo build --release` (needs Rust).

## Known limits

- The frosted blur needs KDE Plasma's Blur effect (System Settings, Desktop
  Effects, Blur) on Linux. Elsewhere, Windows included, the panel is plain
  see-through.
- Windows without a graphics driver (virtual machines, Remote Desktop) gets
  a solid panel drawn on the CPU. If the panel never shows on Windows, set
  the environment variable `HANAMI_RENDERER=software` to force that.
- GNOME shows tray icons only with the AppIndicator extension; the hotkey
  and `hanami --toggle` work without it.
- Minecraft through Prism Launcher instances is planned, not in yet.
