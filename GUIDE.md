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
- Search is forgiving: "hk" finds Hollow Knight by its first letters, and
  when nothing matches exactly, missing letters and small typos ("holow",
  "stradew") still find the game.
- The order: new finds waiting for an answer, then pinned games, then games
  by when you last played them, then everything else from A to Z.
- Each game shows its icon (or its first letter) and a small label saying
  where it came from: steam, epic, gog, amazon, lutris, heroic, app, port,
  rust, or your own label. Pinned games say "pinned", new finds say "new".
- **More for one game:** right-click it, or press Tab. Then pick **Pin to
  top** (or **Unpin**), **Rename** or **Hide**, with a click or with the left
  and right arrows and Enter. Esc goes back.
- **Rename:** type the new name, Enter saves, Esc cancels.
- **Add a game:** the **+** button opens the file picker. Pick the game's
  program (or an AppImage, a script, or on Windows a shortcut); Hanami adds it
  to the settings and lets you name it right away.
- **New finds:** when Hanami finds ports and rewrites by itself, they show
  at the top marked "new", under "Found 2 new games" with **Keep** and
  **Hide**. Each one can also be kept or hidden on its own (right-click or
  Tab). Playing, pinning or renaming a new game keeps it.
- Problems (a typo in the settings, a game that won't start) show as one
  line at the bottom for a few seconds.
- The **?** button copies a prompt with this guide, for an AI assistant.

Pins, names, hidden and added games are saved in the settings file (as
`favourites`, `rename`, `hide` and `[[game]]`), keeping its comments and
layout. When each game was last played and which new finds were kept are
kept apart, in `~/.local/share/hanami/state.toml` on Linux and
`%LOCALAPPDATA%\hanami\state.toml` on Windows. Deleting that file only
forgets the play order and asks about new finds again.

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
find = ["steam", "heroic", "lutris", "apps", "epic", "gog", "ports"]

# Games shown at the top of the list, by name.
favourites = ["Celeste"]

# Your own names for games: the name Hanami found, then yours.
rename = { "Counter-Strike 2" = "CS2" }

# Found games to leave out, by name (case and punctuation don't matter).
hide = ["Some Game"]

# Your own games. Any program can be a game. ~ means the home folder.
[[game]]
name = "My Game"
command = "~/Games/my-game/my-game"   # the program to run
args = ["--fullscreen"]               # optional
dir = "~/Games/my-game"               # optional: folder it runs in
label = "my label"                    # optional: the label shown in the list
icon = "~/Games/my-game/icon.png"     # optional: png, jpeg, ico or svg
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
  Effects, Blur) on Linux. Elsewhere, Windows included, the panel is plain
  see-through.
- Windows without a graphics driver (virtual machines, Remote Desktop) gets
  a solid panel drawn on the CPU. If the panel never shows on Windows, set
  the environment variable `HANAMI_RENDERER=software` to force that.
- GNOME shows tray icons only with the AppIndicator extension; the hotkey
  and `hanami --toggle` work without it.
- Minecraft through Prism Launcher instances is planned, not in yet.
