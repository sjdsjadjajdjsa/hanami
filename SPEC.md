# Hanami v1: spec

Hanami is a game launcher that runs in the system tray and opens a small
panel listing installed games. Built with Slint (software renderer) in Rust,
for Linux and Windows.

## What v1 does

1. **Runs in the tray.** One copy at a time: starting Hanami again just
   opens the running one. `hanami` opens the panel, `hanami --hidden` starts
   in the tray only (for starting with the system). The tray menu has Open,
   Edit settings, Quit.
2. **Opens and closes on demand.** Tray click, the built-in hotkey (default
   `Ctrl+Alt+H`, changeable), or `hanami --toggle` bound to a key in the
   desktop's own shortcut settings (needed on Wayland, where apps can't grab
   keys). The panel opens centred on the screen the mouse is on, with
   keyboard focus, fading in over 140 ms. It never shows in the taskbar.
3. **Finds games by itself**, from every place in the `find` setting, and
   lists each game once, alphabetically, with a small label saying where it
   came from:
   - **steam:** installed Steam games (Steam's own tools left out).
   - **heroic:** Heroic's Epic, GOG and Amazon games and its added programs
     (native and Flatpak), started through Heroic.
   - **lutris:** installed Lutris games (hidden ones left out), started
     through Lutris (Linux).
   - **apps:** games in the Linux app menu: desktop entries in the Game
     category that aren't also Utility, minus launchers whose games are
     found directly (Steam, Heroic, Lutris).
   - **epic** and **gog:** the Epic Games Launcher's and GOG's installed
     games (Windows).
   - Your own entries from the settings file come first and win when the
     same game turns up twice ("Pixel Gun 3D: PC Edition" and "Pixel Gun 3D
     PC Edition" count as one). Names in `hide` are left out.
4. **Type to filter.** Typing narrows the list by name; Backspace widens it.
   Arrows move, Enter or click starts the highlighted game.
5. **Starts the game.** Config games: run the command detached, so closing
   Hanami never closes the game. Steam games: open
   `steam://rungameid/<id>`.
6. **After launching:** one setting, `on_launch`:
   `hide` (default), `keep`, `quit`.
7. **Hides on** Esc, clicking outside the panel, the hotkey again or the
   tray icon again, with the same fade. Key repeat and double presses count
   once. The hotkey and the tray click take focus from the panel just before
   they arrive; that focus loss and the press are one action, so the panel
   closes and stays closed.
8. **AI help prompt.** A small **?** in the header copies
   a prompt (Hanami's GUIDE.md plus this computer's settings path) to paste
   into any AI that can look around the computer. It asks the AI to explain
   what Hanami does, what it found and how to customise it, and to change
   nothing. Hovering the **?** says so in the footer first. `hanami --guide`
   prints the same prompt.
9. **Errors.** A game that fails to start shows one
   line in the panel footer for a few seconds. Nothing pops up elsewhere.

## Config

One TOML file, created with comments on first run:
Linux `~/.config/hanami/config.toml`, Windows `%APPDATA%\hanami\config.toml`.

```toml
hotkey = "Ctrl+Alt+H"
on_launch = "hide"      # hide | keep | quit
find = ["steam", "heroic", "lutris", "apps", "epic", "gog"]
hide = []               # found games you don't want, by name

[[game]]
name = "My Game"
command = "~/Games/my-game/my-game"
args = []
dir = "~/Games/my-game"
label = "my label"
```

Hanami re-reads the file each time the panel opens, so edits show up
without a restart. A broken file keeps the last good list and says so in
the footer.

## Not in v1

Minecraft (v2, through Prism instances), cover art, play time, store pages,
updates, themes, a settings window, starting with the system, Wayland blur,
multiple monitors beyond "open where the mouse is".

## Quality bar

- Hidden: 0 % CPU, under 30 MB memory.
- Open: under 2 % of one core with petals running; under 40 MB.
- From hotkey to panel on screen: under 100 ms.
- Text sharp at 100 % and 150 % scaling.
- Same look and behaviour on Linux (KDE, X11) and Windows 11; blur through
  KWin on Linux and Acrylic on Windows, plain translucency where neither
  exists.

## Done when

- A fresh install on Linux and Windows: run Hanami, press the hotkey, see
  your config games and Steam games, type two letters, press Enter, the
  game starts and the panel is gone.
- Each item in "What v1 does" checked by hand on both systems, and the
  quality numbers measured the same way as the prototypes (see ROADMAP.md).
