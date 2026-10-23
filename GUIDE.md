# Hanami guide

Hanami is a game launcher for Linux and Windows
(<https://github.com/sjdsjadjajdjsa/hanami>, free software under the GPL).
It runs in the system tray and opens a small panel that lists the installed
games. Picking a game starts it and hides the panel.

## Installing and updating

Downloads are at <https://github.com/sjdsjadjajdjsa/hanami/releases/latest>.

- **Linux, AppImage:** `hanami-x86_64.AppImage`. Mark it executable
  (right-click, Properties, "Allow executing" or `chmod +x`) and run it. It
  needs a distribution from 2022 or newer (glibc 2.35: Ubuntu 22.04, Fedora
  36, Mint 21, Debian 12, Arch) and FUSE, which every common desktop Linux
  has; without FUSE, run `./hanami-x86_64.AppImage --appimage-extract-and-run`.
- **Linux, plain binary:** `hanami-linux-x86_64.tar.gz` holds `hanami`,
  README.md, GUIDE.md and LICENSE. Put `hanami` anywhere in your PATH.
- **Windows, installer:** `hanami-setup-x86_64.exe`. Windows SmartScreen
  says the publisher is unknown, because the installer isn't signed; click
  "More info", then "Run anyway". It installs for the
  current user only (no admin rights) into `%LOCALAPPDATA%\Programs\Hanami`,
  adds Hanami to the Start menu and offers a box "Start Hanami when Windows
  starts" (off unless you tick it; it runs `hanami.exe --hidden` after sign-in).
  It is the same entry as **Open at login** in the tray menu; leaving the box
  unticked when installing a new version keeps what you chose there.
  Uninstall from Settings, Apps; that removes the program, the shortcut, the
  startup entry and Hanami's cache, and leaves your settings file and what
  you played.
- **Windows, portable:** `hanami-windows-x86_64.zip`. Unpack it anywhere and
  run `hanami.exe`.

**Updates.** When `online = true` (the default), Hanami asks GitHub at most
once a day whether a newer release is out. If there is one, the tray menu
gets an item "Get Hanami X.Y.Z" that opens the release page in the browser,
and the panel says "Hanami X.Y.Z is out. Get it from the tray menu." once.
Hanami never downloads or installs anything by itself; you install the new
version the same way as the first one. The check remembers the newest
version it saw in `~/.cache/hanami/latest` (Windows:
`%LOCALAPPDATA%\hanami\latest`). `online = false` turns the check off.

## Opening and closing

- **Hotkey:** `Ctrl+Alt+H` by default. Press it again to close.
- **Tray icon:** click to open or close. Right-click for Open, Edit
  settings, Open at login, Quit, and "Get Hanami X.Y.Z" when a newer
  version is out.
- **Command:** `hanami --toggle` opens or closes it. On Wayland, apps can't
  grab keys themselves: on KDE Plasma 6 and GNOME, Hanami adds its hotkey to
  the desktop's own keyboard shortcuts the first time it runs (it shows up
  there as "Hanami"), and from then on that entry is yours: change the key
  there, not in Hanami's settings. On other Wayland desktops bind this
  command to a key yourself.
- **Game controller:** hold Start and Select (the two small middle buttons;
  Menu and View on an Xbox pad, Options and Share or Create on a PlayStation
  pad) together for half a second. The same hold closes it again. See
  [Game controller](#game-controller).
- **Closing:** Esc, clicking somewhere else, the hotkey, or the tray icon.
  With `on_launch = "keep"` clicking somewhere else leaves it open, as the
  game you start takes the focus.
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
  rust, the Minecraft version (like "fabric 1.21.1"), how many instances a
  launcher has, or your own label. Pinned games say "pinned", new finds say "new".
- **More for one game:** right-click it, or press Tab. Then pick **Pin to
  top** (or **Unpin**), **Rename** or **Hide**, with a click or with the left
  and right arrows and Enter. Esc goes back.
- **Rename:** type the new name, Enter saves, Esc cancels.
- **Launchers with games inside:** a row with › (Prism Launcher, for
  Minecraft) opens a list of its own: the launcher itself on top, then its
  instances, last played first and already selected, so Enter twice starts
  it. Esc, Backspace, B on a controller or a click on the title goes back.
  Searching from the whole list finds the instances too, marked "in Prism
  Launcher".
- **Add a game:** the **+** button opens the file picker. Pick the game's
  program (or an AppImage, a script, or on Windows a shortcut); Hanami adds it
  to the settings and lets you name it right away.
- **New finds:** when Hanami finds ports, rewrites or a Minecraft launcher by itself, they show
  at the top marked "new", under "Found 2 new games" with **Keep** and
  **Hide**. Each one can also be kept or hidden on its own (right-click or
  Tab). Playing, pinning or renaming a new game keeps it.
- **Moving the panel:** on Windows, hold Alt or the Windows key and drag it.
  On Linux your desktop does this itself, with the key it uses for moving
  windows (on KDE Plasma 6 and GNOME, the Windows key).
- Problems (a typo in the settings, a game that won't start) show as one
  line at the bottom for a few seconds.
- The **?** button copies a prompt with this guide, for an AI assistant.

Pins, names, hidden and added games are saved in the settings file (as
`favourites`, `rename`, `hide` and `[[game]]`), keeping its comments and
layout. When each game was last played and which new finds were kept are
kept apart, in `~/.local/share/hanami/state.toml` on Linux and
`%LOCALAPPDATA%\hanami\state.toml` on Windows. Deleting that file only
forgets the play order and asks about new finds again.

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
- `controller_buttons` picks other buttons to hold, all together, for the
  half second: any of `start`, `select`, `guide`, `x`, `y`, `lb`, `rb`,
  `lt`, `rt`, `l3`, `r3` (the sticks pressed in), `left` and `right` (on
  the D-pad). A, B, up and down can't be used: the open panel needs them.
  For example `controller_buttons = ["lb", "rb", "start"]`, or
  `["guide"]` where nothing else takes the Guide button.

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
| `apps` | games in the app menu (desktop entries in the Game category that aren't also Utility); Steam, Heroic, Lutris, Prism Launcher, PolyMC and MultiMC themselves are left out because their games are found directly (add a launcher as a `[[game]]` to keep a row for it) | Linux |
| `epic` | Epic Games Launcher games (not DLC, engine tools or uninstalled leftovers) | Windows |
| `gog` | GOG Galaxy and GOG installer games, started through GOG Galaxy when it is installed | Windows |
| `ports` | game ports, recomps and rewrites (see below), games that come with a `hanami-game.toml`, and your own built Rust games from the `projects` folders | Linux, Windows |
| `prism` | Prism Launcher, PolyMC and MultiMC (native, Flatpak or portable) as a row that opens to their Minecraft instances, each started through the launcher so it handles the Microsoft login | Linux, Windows |

The same game found twice (for example in Steam and in the app menu) is
listed once. Games added in the settings file win over found ones.

### Icons

Icons come from files already on the computer; Hanami never downloads them.
They are read in the background, so the panel opens before they are all in.

| Source | Where the icon comes from |
|---|---|
| `steam` | Steam's own small icon for the game (`appcache/librarycache/<id>/`); a bigger copy is used when a desktop shortcut was made for the game (`steam/games/*.ico`, or on Linux `~/.local/share/icons/hicolor/*/apps/steam_icon_<id>.png`) |
| `apps` | the entry's `Icon=`: a file path as it is, or a name looked up as an application icon in the current icon theme (KDE's `kdeglobals` setting, else GTK's, else hicolor), then its parent themes, then hicolor and pixmaps |
| `heroic` | Heroic's downloaded art in its `images-cache` folder, GOG's `goggame-<id>.ico` in the game folder, or on Windows the game's exe |
| `lutris` | Lutris's icon (`lutris_<slug>.png` in the hicolor theme) or its cover in `lutris/coverart`; the wide banners are not used |
| `prism` | the instance's own icon if you picked a custom one in the launcher (its `icons` folder), else the launcher's icon when the icon theme has it (Prism and PolyMC do; MultiMC doesn't), on Windows the launcher's exe |
| `epic` | the game's exe named in the Epic manifest (Windows) |
| `gog` | `goggame-<id>.ico` in the game folder, else the game's exe (Windows) |
| your `[[game]]` | the `icon` setting; without one, on Windows, the icon inside the `command` program when it is an exe |

Picture files can be png, jpeg, ico, svg, webp or bmp; on Windows an exe
works too. Wide pictures are shrunk to fit the square, not cropped.
`hanami --list --verbose` prints the icon file picked for each game, or
`(no icon)`.

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
is one. Games run from the project's root folder with `CARGO_MANIFEST_DIR`
set to the package's folder, like `cargo run`, so engines such as Bevy find
their `assets` folder.

The name comes from `[package.metadata.hanami] name`, else from the package
name made readable: `kite-game` is `Kite Game`, `paper-gun-3d-rs` is
`Paper Gun 3D`. The metadata table can also hold `args = [...]` and
`icon = "path/relative/to/Cargo.toml"`. Label: `rust`. Folders named
`backup` (or containing it), `target`, `vendor`, `node_modules` and hidden
folders are skipped.

The `ports` search runs in the background: the panel shows the last result
at once and a new search starts when that result is about a minute old, so
a freshly downloaded port can take a minute (or two panel opens) to show.
`hanami --list` searches right away.

### Minecraft

Prism Launcher (and PolyMC and MultiMC, the launchers it grew out of) is
one row; Enter opens its instances. Each instance starts with the
launcher's own command (`prismlauncher --launch <instance folder>`,
through `flatpak run` for the Flatpak). The launcher opens, signs in with
your Microsoft account and starts the game, so Hanami never sees an
account. The launcher's row inside that list just opens the launcher, for
making new instances.

Where Hanami looks:

- Prism: `~/.local/share/PrismLauncher` and the Flatpak's
  `~/.var/app/org.prismlauncher.PrismLauncher/data/PrismLauncher` on Linux;
  `%APPDATA%\PrismLauncher` on Windows, with the program from the installer
  (`%LOCALAPPDATA%\Programs\PrismLauncher` or `C:\Program Files\PrismLauncher`).
- PolyMC: `~/.local/share/PolyMC` and its Flatpak (`org.polymc.PolyMC`).
- MultiMC: `~/.local/share/multimc` (the AUR package).
- Portable copies (a folder with `prismlauncher.cfg`, `polymc.cfg` or
  `multimc.cfg` next to the program): in your home folder, `~/Games`,
  `~/Applications`, `~/AppImages`, Downloads, the Desktop, `/opt` (Linux),
  `C:\Games`, `D:\Games` and `C:\MultiMC` (Windows), the `folders` setting,
  and one folder deep in each (hidden folders and links are skipped).
- Prism's AppImage uses the same data folder as the package; when
  `prismlauncher` isn't installed, a `PrismLauncher*.AppImage` in those
  places starts the instances.

A launcher whose data is still there but whose program is gone (removed,
or an AppImage moved elsewhere) is reported in the panel; put its program
in one of the places above, or remove `prism` from `find`.

A custom instance folder set in the launcher (`InstanceDir`) is followed.
An instance's name is its name in the launcher; one still named after its version
reads "Minecraft 1.21.1". The same name in two launchers gets the
launcher after it, like "Minecraft 26.3 (Prism Flatpak)", and a copied
instance gets its folder name. Launchers count for this as long as their
data is there, so names don't change when one is uninstalled. The label is
the mod loader (fabric, forge, neoforge, quilt) or "minecraft", then the
version. A launcher found for the first time waits for **Keep** or **Hide**
like other new finds (opening it keeps it); instances added later just show
up inside. Pins, renames and hides work on instances like on any game, and
hiding the launcher's row hides its instances.

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
find = ["steam", "heroic", "lutris", "apps", "epic", "gog", "ports", "prism"]

# Games shown at the top of the list, by name.
favourites = ["Celeste"]

# Your own names for games: the name Hanami found, then yours.
rename = { "Counter-Strike 2" = "CS2" }

# Found games to leave out, by name (case and punctuation don't matter).
hide = ["Some Game"]

# Game controller: hold Start and Select together for half a second to open
# or hide the panel; in the panel, up and down move, A starts, B hides.
controller = true

# The buttons held together to open the panel.
controller_buttons = ["start", "select"]

# Extra folders to search for ports and games with a hanami-game.toml.
folders = ["~/Emulation/ports"]

# Folders with your own Rust game projects; built games are offered.
projects = ["~/Projects"]

# Hanami goes online at most once a day, only to GitHub: for the newest
# list of known ports and to check for a new version. false = never.
online = true

# Your own games. Any program can be a game. ~ means the home folder.
[[game]]
name = "My Game"
command = "~/Games/my-game/my-game"   # the program to run
args = ["--fullscreen"]               # optional
dir = "~/Games/my-game"               # optional: folder it runs in
label = "my label"                    # optional: the label shown in the list
icon = "~/Games/my-game/icon.png"     # optional: png, jpeg, ico or svg
env = { MANGOHUD = "1" }              # optional: extra environment variables
```

Games started by Hanami keep running when Hanami closes.

## Commands

| Command | What it does |
|---|---|
| `hanami` | open the panel (starts Hanami if needed) |
| `hanami --hidden` | start in the tray only (what the login entry runs) |
| `hanami --toggle` | open or close the panel |
| `hanami --quit` | close the running Hanami (the tray menu's Quit does the same) |
| `hanami --list` | print every game the panel would show, with its label (with `--verbose`, also its icon file); a place that is there but couldn't be read is named at the end |
| `hanami --guide` | print the AI prompt the **?** button copies |
| `hanami --verbose` | print what happens (opening, focus, where games were found, how long the ports search took) for bug reports |
| `hanami --snapshot picture.png` | draw the panel with sample games into a picture, without opening it |

## Starting with the computer

Right-click the tray icon and pick **Open at login**. A tick shows it is on;
pick it again to turn it off. On Linux this writes
`~/.config/autostart/hanami.desktop` (pointing at the AppImage when you run
one); on Windows it sets the same startup entry as the installer's tick box.
Hanami then starts in the tray only, without opening the panel.

## Changing the look

Two text files decide the look, and the next time the panel opens it shows
the change. An AI can write both, so "make it autumn with maple leaves" is a
reasonable thing to ask it.

**1. The `[theme]` block in the settings file** (`config.toml`):

```toml
[theme]
panel = "#17141db8"   # the panel's colour; the last two digits are how solid
text = "#ece6ee"      # game names and the title
dim = "#9b93a3"       # labels and hints
accent = "#f4b6c8"    # the selected row, the petals' tint in the highlight
petals = 24           # how many petals fall (0 to 200)
speed = 1.0           # how fast they fall; 0.5 is half as fast
size = 1.0            # how big they are; 1.5 is half as big again
drift = 1.0           # how far they sway sideways; leaves tumble, snow wobbles
spin = 1.0            # how much they turn; 0 keeps them upright
tints = []            # colours to paint the petals in, taken in turn; empty
                      # keeps the picture's own colours
dots = 0              # specks of the accent colour drifting up (0 to 100):
                      # pollen, embers, fine snow
```

Petals come in all sizes on their own: small ones are fainter and slower,
as if further away. Suggested settings, since the picture alone isn't
enough for a look to feel right:

| look | petals | speed | size | drift | spin | tints | dots |
|---|---|---|---|---|---|---|---|
| sakura (default) | 24 | 1.0 | 1.0 | 1.0 | 1.0 | none | 0 |
| autumn leaves | 16 | 0.7 | 1.8 | 1.6 | 1.4 | `["#e0602a", "#c8401c", "#f0a040", "#9a3410"]` | 12 |
| snow | 18 | 0.6 | 1.3 | 1.3 | 0.3 | `["#ffffff", "#dceeff", "#bfe0ff"]` | 24 |

With `tints` the picture is painted in those colours by its brightness:
darker parts (a vein, a shadow) stay darker, but its own colours don't
show; leave `tints` empty for a petal with two colours of its own.

Colours are `"#rrggbb"` or `"#rrggbbaa"`. Keep `panel` between `80` and
`e0` at the end so it stays see-through but readable, and keep `text`
light on a dark panel (or dark on a light one). A wrong value keeps the
old look and the panel says which line is wrong.

**2. `petal.svg` (or `petal.png`) next to the settings file.** When it
exists, it is the falling shape instead of the sakura petal. Delete it to
get the petal back. It can be an SVG, which is text an AI can write, or a
png/webp/jpeg with a see-through background, from a picture AI or anywhere
else (an emoji picture, say). Rules that keep a petal clear and light:

- An SVG is one plain file: a square `viewBox`, one or a few `path`,
  `circle` or `ellipse` elements with `fill` or `stroke` colours, nothing
  else. No text, no pictures inside it, no links to other files, no scripts,
  no filters, no gradients.
- Under 512 KB; a petal is a few lines, or a png of 64 to 256 pixels.
- The shape should fill most of the box and be clear at 12 pixels: a leaf,
  a petal, a snowflake, a star. Fine detail disappears at that size; a
  detailed shape like a leaf wants `size = 1.8` and fewer petals.

Hanami refuses a file over 512 KB or one it can't draw ("Couldn't read
petal.svg: ...") and the sakura petal stays.

**For an AI changing the look:** edit only `[theme]` and `petal.svg`, nothing
else in the settings file; keep the keys above and their ranges; start
from the table's settings for the kind of look asked for; change only what
was asked for; then say what you changed. To check the result,
`hanami --snapshot look.png` draws the panel with the current look into a
picture without opening it.

Shapes drawn by hand from coordinates rarely look right; emoji pictures
do, since they are drawn to be clear at 16 pixels. The two examples
below are Microsoft's Fluent Emoji (MIT licence), as they come. The
maple leaf, with the autumn row of the table above:

```svg
<svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M29.7164 17.8025L27.3964 17.3625C27.2564 17.3325 27.1864 17.1725 27.2564 17.0525L29.4164 13.5825C29.5064 13.4325 29.3964 13.2525 29.2264 13.2625L25.1564 13.6325C25.0164 13.6425 24.8964 13.5124 24.9364 13.3724L25.5764 11.1325C25.6264 10.9525 25.4264 10.8025 25.2664 10.9025L20.9164 13.6525C20.7664 13.7425 20.5764 13.6225 20.5964 13.4525L21.8764 4.12245C21.8964 3.95245 21.7164 3.8225 21.5664 3.9225L18.2764 5.9225C18.1764 5.9825 18.0364 5.94248 17.9864 5.84248L16.1264 2.1125C16.0464 1.9625 15.8364 1.9625 15.7564 2.1125L13.8964 5.84248C13.8464 5.95248 13.7064 5.99251 13.6064 5.93251L10.2064 3.9225C10.0564 3.8325 9.86642 3.96246 9.89642 4.13246L11.5264 13.4525C11.5564 13.6225 11.3664 13.7525 11.2164 13.6625L6.60642 10.8925C6.44642 10.7925 6.24641 10.9424 6.29641 11.1224L6.94642 13.3825C6.98642 13.5225 6.87641 13.6625 6.72641 13.6425L2.65641 13.2725C2.48641 13.2525 2.37642 13.4425 2.46642 13.5925L4.62642 17.0625C4.70642 17.1825 4.63642 17.3524 4.48642 17.3724L2.16642 17.8125C1.98642 17.8425 1.93642 18.0825 2.09642 18.1925L8.63642 22.4825C8.80642 22.5925 8.84642 22.8125 8.73642 22.9825L6.80642 25.7325C6.71642 25.8625 6.84642 26.0425 6.99642 25.9825L15.3764 22.9225C15.7364 22.7925 16.1364 22.7925 16.4964 22.9225L24.8764 25.9825C25.0264 26.0425 25.1664 25.8625 25.0664 25.7325L23.1364 22.9825C23.0264 22.8225 23.0664 22.5925 23.2364 22.4825L29.7764 18.1925C29.9464 18.0725 29.8964 17.8325 29.7164 17.8025Z" fill="#F8312F"/>
<path d="M15.9464 11.2725C16.4987 11.2725 16.9464 11.7202 16.9464 12.2725V20.3934L22.3889 17.5933C22.88 17.3407 23.4829 17.534 23.7356 18.0251C23.9882 18.5162 23.7949 19.1191 23.3038 19.3718L16.9464 22.6426V28.9725C16.9464 29.5248 16.4987 29.9725 15.9464 29.9725C15.3941 29.9725 14.9464 29.5248 14.9464 28.9725V22.6426L8.58886 19.3718C8.09776 19.1191 7.90447 18.5162 8.15714 18.0251C8.4098 17.534 9.01275 17.3407 9.50384 17.5933L14.9464 20.3935V12.2725C14.9464 11.7202 15.3941 11.2725 15.9464 11.2725Z" fill="#CA0B4A"/>
</svg>
```

The snowflake, with the snow row (its `tints` paint it white):

```svg
<svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M23.5638 18.9L28.6756 17.54C29.229 17.39 29.8126 17.69 29.9636 18.25C30.1145 18.81 29.7824 19.37 29.229 19.52L26.1197 20.35L28.3435 21.62C28.8265 21.9 28.9976 22.51 28.7158 22.99C28.4341 23.47 27.8203 23.64 27.3373 23.36L25.1135 22.09L25.9486 25.18C26.0996 25.74 25.7776 26.3 25.2141 26.45C24.6506 26.6 24.0871 26.27 23.9361 25.72L22.5677 20.64L20.2533 19.31C19.5389 20.1 18.593 20.68 17.5062 20.9V23.53L21.2495 27.25C21.652 27.65 21.652 28.31 21.2495 28.71C20.847 29.11 20.1829 29.11 19.7804 28.71L17.5062 26.45V29C17.5062 29.55 17.0534 30 16.5 30C15.9466 30 15.4938 29.55 15.4938 29V26.46L13.2196 28.72C12.8171 29.12 12.153 29.12 11.7505 28.72C11.348 28.32 11.348 27.66 11.7505 27.26L15.4938 23.54V20.91C14.3969 20.69 13.4611 20.11 12.7467 19.32L10.4424 20.64L9.07391 25.72C8.92298 26.27 8.34942 26.6 7.79598 26.45C7.24255 26.3 6.91049 25.73 7.06142 25.18L7.89661 22.09L5.6728 23.37C5.18981 23.64 4.576 23.48 4.29425 23C4.0125 22.52 4.18356 21.91 4.6565 21.65L6.8803 20.37L3.771 19.54C3.21757 19.39 2.88551 18.82 3.03644 18.27C3.18738 17.72 3.76094 17.39 4.31437 17.54L9.4261 18.9L11.7405 17.57C11.5694 17.08 11.4587 16.55 11.4587 16C11.4587 15.45 11.5694 14.92 11.7405 14.45L9.4261 13.12L4.31437 14.48C3.75088 14.63 3.18738 14.3 3.03644 13.75C2.88551 13.19 3.21757 12.63 3.771 12.48L6.8803 11.65L4.6565 10.37C4.18356 10.09 4.0125 9.48 4.29425 9C4.56594 8.52 5.18981 8.36 5.66274 8.63L7.89661 9.91L7.06142 6.82C6.91049 6.27 7.24255 5.71 7.79598 5.56C8.34942 5.41 8.91291 5.74 9.06385 6.29L10.4323 11.37L12.7366 12.69C13.4511 11.9 14.3969 11.32 15.4837 11.1V8.47L11.7405 4.75C11.338 4.35 11.338 3.69 11.7405 3.29C12.143 2.89 12.8071 2.89 13.2096 3.29L15.4837 5.55V3C15.4837 2.45 15.9365 2 16.4899 2C17.0434 2 17.4962 2.45 17.4962 3V5.55L19.7703 3.29C20.1728 2.89 20.8369 2.89 21.2394 3.29C21.6419 3.69 21.6419 4.35 21.2394 4.75L17.4962 8.47V11.1C18.5829 11.32 19.5288 11.9 20.2332 12.68L22.5475 11.35L23.916 6.27C24.067 5.72 24.6405 5.39 25.194 5.54C25.7474 5.69 26.0795 6.26 25.9285 6.81L25.0933 9.9L27.3171 8.63C27.8001 8.36 28.4139 8.52 28.6957 9C28.9674 9.48 28.8064 10.09 28.3334 10.36L26.1096 11.63L29.2189 12.46C29.7724 12.61 30.1044 13.18 29.9535 13.73C29.8026 14.28 29.229 14.61 28.6756 14.46L23.5638 13.1L21.2495 14.43C21.4205 14.92 21.5312 15.45 21.5312 16C21.5312 16.55 21.4205 17.07 21.2495 17.57L23.5638 18.9ZM19.5087 16C19.5087 14.3431 18.1572 13 16.49 13C14.8228 13 13.4712 14.3431 13.4712 16C13.4712 17.6569 14.8228 19 16.49 19C18.1572 19 19.5087 17.6569 19.5087 16Z" fill="#00A6ED"/>
</svg>
```

Sizes, spacing and corner rounding are not settings; they're in
`hanami/ui/hanami.slint` (`Tokens`), and `DESIGN.md` explains the rules
behind them.

## Known limits

- The frosted blur needs KDE Plasma's Blur effect (System Settings, Desktop
  Effects, Blur) on Linux, on X11 or Wayland. Elsewhere, Windows included,
  the panel is plain see-through.
- Windows without a graphics driver (virtual machines, Remote Desktop) gets
  a solid panel drawn on the CPU. If the panel never shows on Windows, set
  the environment variable `HANAMI_RENDERER=software` to force that.
- GNOME shows tray icons only with the AppIndicator extension; the hotkey
  and `hanami --toggle` work without it.
