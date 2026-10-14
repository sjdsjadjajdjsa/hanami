# Hanami roadmap

What version 1 does is in SPEC.md, how it looks in DESIGN.md, and how to
use it in GUIDE.md.

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
- **Controller (0.2):** hold Start and Select to open; D-pad, A and B in the
  panel. No CPU while idle.
- **Packages and updates (0.2):** AppImage, a per-user Windows installer, an
  AUR package ready to publish, and a tray item when a new version is out.
- **Measured** (Linux, KDE on X11): hidden 0 % CPU and about 35 MB; open with
  petals 0-1 % CPU; looking through every game source takes a few
  milliseconds, the ports scan runs in the background.

## Next

1. **Publish the AUR package** (`packaging/README.md` has the steps; needs
   an AUR account).
2. **Windows:** Acrylic blur behind the panel; the Epic and GOG sources
   checked against more installs.
3. **Controller:** more pads checked, and a way to change the open button.

## Later

- **Minecraft** through Prism Launcher instances, so Prism handles the
  Microsoft login.
- **Desktop widget mode:** the panel pinned to the desktop, below other
  windows, on every workspace, movable and resizable, near 0 % CPU while
  always visible. X11 desktops and Windows first; Wayland through XWayland.
- **Themes.**
