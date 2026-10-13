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
- **Game controller:** hold Start and Select (the two small middle buttons;
  Menu and View on an Xbox pad, Options and Share or Create on a PlayStation
  pad) together for half a second. The same hold closes it again. See
  [Game controller](#game-controller).
- **Closing:** Esc, clicking somewhere else, the hotkey, or the tray icon.
- Only one Hanami runs at a time; starting it again opens the running one.

## In the panel

- Type to search. Arrow keys move, Enter or a click starts the game.
- Each game has a small label saying where it came from: steam, epic, gog,
  amazon, lutris, heroic, app, or your own label.
- Problems (a typo in the settings, a game that won't start) show as one
  line at the bottom for a few seconds.
- The **?** button copies a prompt with this guide, for an AI assistant.

## Game controller

Any controller the system sees works (on Windows, those Windows treats as
Xbox-style controllers; PlayStation pads work there through Steam or
DS4Windows). It can be plugged in while Hanami runs.

- **Hidden:** holding Start and Select together for half a second opens the
  panel. Nothing else on the controller does anything while the panel is
  hidden, so a game or emulator keeps the controller to itself.
- **Open:** the D-pad or the left stick moves up and down (hold to keep
  moving), A (the bottom button, Cross on a PlayStation pad) starts the
  game, B (the right button, Circle) hides the panel. Holding Start and
  Select again hides it too.
- `controller = false` in the settings turns all of this off.

Why Start and Select: the Guide button (the Xbox or PlayStation logo) is
taken. Steam opens its overlay or Big Picture on it, Windows opens the Game
Bar, and Steam often keeps the controller for itself while it runs. Holding
one button is a common game action. Start and Select together, held, is
bound by nothing well known, and the half-second hold keeps a quick press
inside a game from opening the panel.

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

# Game controller: hold Start and Select together for half a second to open
# or hide the panel; in the panel, up and down move, A starts, B hides.
controller = true

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
