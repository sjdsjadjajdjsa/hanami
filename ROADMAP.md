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
- **Measured** (Linux, KDE on X11): hidden 0 % CPU and about 27 MB; open with
  petals 0-1 % CPU and about 30 MB; looking through every game source takes
  a few milliseconds.

## Next

1. **Add games from the panel:** a **+** that opens the system file picker,
   saves the game to the settings without disturbing anything else in the
   file, and a right-click to rename or remove.
2. **Windows check:** blur (Acrylic), centring on the mouse's screen, and
   the Epic and GOG sources tested on real installs.
3. **Packages:** an AUR package and an AppImage for Linux, an installer for
   Windows, built automatically for each release.
4. ~~**Site**~~ at <https://hanami.lilygrove.dev> (source in `site/`).

## Later

- **Minecraft** through Prism Launcher instances, so Prism handles the
  Microsoft login.
- **Desktop widget mode:** the panel pinned to the desktop, below other
  windows, on every workspace, movable and resizable, near 0 % CPU while
  always visible. X11 desktops and Windows first; Wayland through XWayland.
- **Themes.**
