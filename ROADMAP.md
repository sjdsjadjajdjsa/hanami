# Hanami roadmap

What version 1 does is in SPEC.md (with the targets it has to meet), how
it looks in DESIGN.md, and how to use it in GUIDE.md.

## Done

- **The panel:** a small rounded, see-through window (Slint, software
  renderer) with sakura petals at 30 fps, opened from the tray, a hotkey or
  `hanami --toggle`. Fades in and out over 140 ms, stays out of the taskbar,
  hides on Esc, a click elsewhere, the hotkey or the tray icon. One copy at
  a time.
- **Finding games:** Steam, Heroic (Epic, GOG, Amazon, added programs),
  Lutris, games in the Linux app menu, and the Epic Games Launcher and GOG
  on Windows. Each game is listed once; `hide` leaves games out; your own
  entries win.
- **Ask your AI:** the **?** button copies a prompt with GUIDE.md so any AI
  that can see the computer explains Hanami without changing anything.
- **Your list (0.2):** pin, rename and hide from the panel (Tab or
  right-click), **+** to add a program with the system file picker, settings
  edits that keep comments, games played last first, search by first letters
  and with small typos.
- **Icons (0.2):** from Steam, the app menu's icon theme, Heroic, Lutris and,
  on Windows, the game's exe; decoded in the background.
- **Ports and rewrites (0.2):** a list of known ports on GitHub that anyone
  can add to (PORTS.md), a `hanami-game.toml` port makers can ship, an
  opt-in scan of a projects folder for Rust games; new finds wait for Keep
  or Hide.
- **Minecraft (0.2.9):** Prism Launcher, PolyMC and MultiMC (native,
  Flatpak, portable) as a row that opens to their instances, each started
  through the launcher so it handles the Microsoft login.
- **Controller (0.2):** hold Start and Select to open; D-pad, A and B in the
  panel. No CPU while idle.
- **Packages and updates (0.2):** AppImage, a per-user Windows installer, an
  AUR package ready to publish, and a tray item when a new version is out.
- **Your look (0.2.8):** a `[theme]` block (colours, how many petals fall,
  how fast, how big, how they sway, spin and are tinted, specks drifting
  up) and a `petal.svg` or `petal.png` next to the settings, which an AI
  can write; GUIDE.md has the rules the `?` prompt points the AI at, with
  settings for sakura, autumn leaves and snow. Petals come in all sizes,
  the small ones faint and slow, and turn over as they fall.
- **Open at login (0.2.5):** a tray menu item that adds or removes the login
  entry (autostart desktop file on Linux, the installer's Run key on Windows).
- **KDE on Wayland (0.2.5):** the panel is see-through (a patched softbuffer,
  see `third_party/softbuffer/PATCH.md`), gets KWin's frosted blur, stays out
  of the taskbar and the window switcher, and the tray's hidden helper window
  no longer shows up as a task. Checked on Kubuntu 26.04; GNOME on Wayland
  is see-through too now.
- **Measured before 0.2.14** (Linux, KDE on X11, a real desktop; the
  machine and library weren't written down): hidden 0 % CPU and about
  35 MB; open with petals 0-1 % CPU. These are older than the targets in
  SPEC.md and aren't a reference-desktop result.
- **Windows** runs on real machines, not only under Wine.
- **0.2.14, ready but not released:** sturdier Epic (the launcher's own
  data folder, games left behind by uninstalls skipped, manifests with a
  byte order mark read) and GOG (a missing `exe` filled in from
  `goggame-<id>.info`, games started through GOG Galaxy when it is
  installed); `controller_buttons` to choose the buttons that open the
  panel; only the rows in view are built, so a big library costs about as
  much as a small one; the panel shows the games found last and looks for
  new ones after it is up; on X11 the hotkey no longer wakes Hanami every
  50 ms; with `controller = false` no controller work runs. It waits on a
  basic check on real Windows (see "Waiting on real hardware").
- **0.2.15, in code but turned off:** Acrylic blur behind the panel on
  Windows 11 22H2 and newer (`ACRYLIC` in `desktop/src/lib.rs`). Until it
  has been checked on real machines, Windows gets the plain panel.
- **Checked on five Linux desktops** (live ISOs in QEMU, Oct 2026): the
  AppImage runs without libfuse2, finds the app-menu games and a Steam
  library, opens from the tray and from `hanami --toggle`, and starts an
  app-menu game and a Steam game (`steam://` through the system handler).

  | Desktop | Tray | Panel | Hotkey |
  |---|---|---|---|
  | Kubuntu 26.04, KDE Plasma, Wayland | yes, click opens | yes (fixed, see below) | yes (since 0.2.6) |
  | Ubuntu 26.04, GNOME, Wayland | yes (Ubuntu's indicator), click shows the menu | yes (fixed) | yes (since 0.2.6) |
  | Fedora 44, GNOME, Wayland | none: stock GNOME has no tray | yes (fixed) | yes (since 0.2.6, same way as Ubuntu; not re-checked) |
  | Xubuntu 26.04, Xfce, X11 | yes, click shows the menu | yes | yes |
  | Linux Mint 22.3, Cinnamon, X11 | yes, click opens | yes | yes |

  Found and fixed: on Wayland, a Hanami started `--hidden` (the normal way)
  never showed its panel; v0.2.3 has this bug on KDE and GNOME. Since 0.2.6
  the hotkey works on KDE Plasma and GNOME under Wayland too: Hanami adds it
  to the desktop's own shortcuts. Elsewhere on Wayland the panel says once
  to bind `hanami --toggle` to a key.

## Measured

Targets are in SPEC.md, under "Quality bar". These are results, and none
of them is from the reference desktop yet.

**0.2.14 on a shared cloud machine** (commit `1ea8090`, no local changes,
24 Oct 2026). Only for comparing runs with each other: it doesn't decide
whether the CPU target is met.

- Machine: 4 logical cores (Intel Xeon; the machine hides the exact
  model), 16 GB, no GPU, Ubuntu 24.04, Linux 6.18, in a container.
- Screen: Xvfb at 1920x1080, scale 1, no window manager, no compositor, no
  blur. Hanami draws with the CPU.
- Libraries from `tools/bench.py`: `large` is 1,350 games (800 Steam, 150
  in the app menu among 400 other programs, 300 Heroic, 100 Lutris);
  `typical` is 200 (110, 30 among 80, 40, 20). Every game has an icon.
- CPU: Hanami's own time over 10 s, in % of one logical core, the X
  server's work not counted. Open means open and idle, 1 s after it drew,
  no input. Memory: RSS (PSS in brackets) in MB.
- Run with `python3 tools/bench.py --library large|typical --petals 24|0`.
  The saved results, with everything about each run, are in
  [tools/results](tools/results).

| Library | Petals | Open CPU | Hidden CPU | Memory loaded | Open | Hidden after opening |
|---|---|---|---|---|---|---|
| 1,350 games | 24 at 30 fps | 3.2 % | 0.0 % | 25.2 (22.4) | 33.9 (30.7) | 34.9 (31.7) |
| 1,350 games | none | 0.2 % | 0.0 % | 25.1 (22.2) | 33.7 (30.6) | 34.9 (31.7) |
| 200 games | 24 at 30 fps | 3.2 % | 0.0 % | 24.5 (21.6) | 28.4 (25.3) | 28.9 (25.6) |
| 200 games | none | 0.3 % | 0.1 % | 24.5 (21.7) | 28.5 (25.4) | 28.8 (25.6) |

| Library | Hotkey to first pixel | `--toggle` to first pixel | Cold start to first pixel | Looking for games, each open |
|---|---|---|---|---|
| 1,350 games | 8.3 ms | 11.3 ms | 58.6 ms | 19 ms |
| 200 games | 3.9 ms | 6.7 ms | 37.1 ms | 2 ms |

What this says:

- The library's size no longer changes the CPU use: before only the rows in
  view were built, 1,350 games took 42 %.
- The petals cost about 3 % of a core on this machine. Earlier runs the same
  day, with the same drawing code, read 2.4 to 2.6 %, so this machine varies by about a
  point between runs. Whether the petals meet the 2 % target is for the
  reference desktop to say. 24 petals at 30 fps stay as they are until that
  says otherwise.
- With the typical library Hanami uses 28.9 MB hidden after opening and
  28.4 MB open, inside the 30 MB and 40 MB targets on this machine. With
  1,350 games it is 34.9 MB hidden, over 30 MB. Icons stay decoded after
  the first open; that is kept for 0.2.14.
- The hotkey time runs from Ctrl+Alt+H sent through XTest to the first
  pixel in the X server, not to the monitor. Looking for games happens
  after the panel is up, so it doesn't add to opening. Starting a game
  isn't measured.

**Hidden: what runs on a timer** (checked in the code and by counting each
thread's wake-ups over 10 s while hidden, Linux X11, 0.2.14):

- Hiding stops the petal clock on every way the panel hides (Esc, a click
  elsewhere, hotkey, tray, controller, after a launch, quitting). Showing
  starts it once; reopening mid-fade keeps the one clock. The window is
  really hidden, so nothing redraws, and no Slint animation runs on.
- No other timers or polling of Hanami's own: the update check runs at
  start and at most once a day; the IPC, icon and game-finding threads wait
  for work; the controller waits on Linux events.
- Fixed in 0.2.14: global-hotkey's X11 loop, which by its code wakes 20
  times a second, and gilrs's rumble thread, also 20 a second. Counted with
  the hotkey already fixed, a hidden Hanami went from 220 wake-ups in 10 s
  to 20 once the rumble thread was gone.
- Left: the `blocking` thread pool used by zbus (the tray and Slint) checks
  for work twice a second. On Windows, gilrs asks XInput 100 times a second
  while controller support runs, hidden or not; `controller = false` stops
  it from starting. Not checked yet on Wayland and Windows by counting.

## Waiting on real hardware

Results come from the owner; nothing here is done until they are in.

**Linux reference desktop**

- Run `tools/bench.py` on the real PC, `--library typical` and `--library
  large`, and with `--note machine="..."` for anything the script can't
  tell. `--display :0` uses the desktop's own screen (X11 only) instead of
  Xvfb.
- Open and idle with 24 petals at 30 fps against the 2 % target; hidden
  behaviour; memory with the typical library.
- Hotkey to the first visible frame against 100 ms, timed on the screen.

**Windows, before 0.2.14 is released**

- Panel toggle, the hotkey, and starting a game.
- Epic and GOG against real installed libraries.
- `controller_buttons` with a real controller.
- How fast the panel opens.

**Windows, before Acrylic ships in 0.2.15**

- Acrylic on Windows 11 22H2 and 24H2 where available; any version not
  checked is written down as not covered.
- How it looks, opening and closing, and the blur while dragging the panel.
- Hotkey to the first visible frame with the blur on.

**Packages:** the AUR package waits for the owner's AUR account.

## Next

1. **Check the new Windows parts on a real machine** (see above): first
   what 0.2.14 needs, then Acrylic (the blur keeps to the rounded corners,
   no solid flash on opening, light and dark panel colours) for 0.2.15.
2. **Works everywhere:** other Linux desktops (MATE, Budgie, LXQt,
   Hyprland).
3. **Publish the AUR package** (`packaging/README.md` has the steps; needs
   an AUR account).
4. **Controller:** more pads checked.

## Open questions

Not blocking anything above:

- Which desktop is the reference, and what does it measure?
- Does the memory result call for work, or for a proposed change to the
  target?
- Do big libraries need a limit on cached icons, and which ones go first?
- What Windows coverage and Acrylic fixes does 0.2.15 need?
- Does the reference desktop show the petals need cheaper drawing?
