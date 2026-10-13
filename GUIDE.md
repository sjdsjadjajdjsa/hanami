# Hanami guide

Hanami is a small game launcher for Linux and Windows
(<https://github.com/sjdsjadjajdjsa/hanami>, free software under the GPL).
It lives in the system tray and opens as a small rounded, see-through panel with sakura
petals drifting behind a list of games. You pick a game, it starts, and
Hanami gets out of the way.

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
- Each game has a quiet label saying where it came from: steam, epic, gog,
  amazon, lutris, heroic, app, or your own label.
- Problems (a typo in the settings, a game that won't start) show as one
  line at the bottom for a few seconds.
- The **?** button copies a prompt like the one that brought you here.

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

The same game found twice (for example in Steam and in the app menu) is
listed once. Games added in the settings file win over found ones.

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
find = ["steam", "heroic", "lutris", "apps", "epic", "gog"]

# Found games to leave out, by name (case and punctuation don't matter).
hide = ["Some Game"]

# Your own games. Any program can be a game. ~ means the home folder.
[[game]]
name = "My Game"
command = "~/Games/my-game/my-game"   # the program to run
args = ["--fullscreen"]               # optional
dir = "~/Games/my-game"               # optional: folder it runs in
label = "my label"                    # optional: the quiet label in the list
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
| `hanami --verbose` | print what happens (opening, focus, where games were found) for bug reports |
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
  Effects, Blur) on Linux, or Windows 11. Elsewhere the panel is plain
  see-through.
- GNOME shows tray icons only with the AppIndicator extension; the hotkey
  and `hanami --toggle` work without it.
- Minecraft through Prism Launcher instances is planned, not in yet.
