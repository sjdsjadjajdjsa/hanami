# Ports and Hanami

Hanami finds PC ports of console games, recompilations and rewrites by
itself. Two ways to make that work for a port: an entry in the shared list
(for ports people download from the project's own page), or a small file the
port ships next to its program (for anything else, without asking us).

## Adding a port to the list

The list is `ports.toml` at the root of this repository. Hanami ships a copy
and fetches the newest one from GitHub once a day, so a change here reaches
every Hanami within a day of being merged, without a new release.

1. Fork the repository and open `ports.toml`.
2. Add a `[[port]]` entry:

   ```toml
   [[port]]
   name = "Zelda 64: Recompiled"
   url = "https://github.com/Zelda64Recomp/Zelda64Recomp"
   linux = ["Zelda64Recompiled", "Zelda64Recompiled-*.appimage"]
   windows = ["Zelda64Recompiled.exe"]
   flatpak = ["io.github.zelda64recomp.zelda64recomp"]
   ```

   - `name`: what the panel shows. Use the name the port's own `.desktop`
     file or Flatpak uses, so Hanami lists the game once when it also turns
     up in the app menu (case and punctuation don't matter for that).
   - `url`: the project page.
   - `linux`, `windows`: the program's file names, as released. Case doesn't
     matter. `*` stands for anything, for names that carry a version
     (`SoH-*.appimage`). Be exact: a wrong match puts a stranger in
     someone's game list. Hanami only looks at executable files on Linux and
     `.exe` files on Windows, in `~/Games`, `~/Downloads`, a few other usual
     places and the user's own folders.
   - `flatpak`: Flatpak app ids, if any.
   - `beside` (optional): files of which one must sit next to the program.
     Use it when the program's name could belong to something else
     (`Starship.exe` needs `starship.o2r`).

3. Raise `version` at the top by one.
4. Check that it parses: `cargo test -p hanami list` in a clone, or just
   `python3 -c "import tomllib; tomllib.load(open('ports.toml','rb'))"`.
5. Open a pull request. Say where the file names come from (a release page
   or the build's output), so they can be checked.

Ports need the user's own game files (ROMs, data files); Hanami doesn't check
for those, it only finds the program.

## Shipping a hanami-game.toml

A port or any other game can tell Hanami about itself with a file called
`hanami-game.toml` next to its program. Hanami finds it in the same places as
the list's programs (and in the user's `projects` folders) and shows the game
with no list entry needed.

```toml
name = "Ship of Harkinian"   # shown in the panel
command = "soh.appimage"     # the program, relative to this file
args = ["--fullscreen"]      # optional
icon = "icon.png"            # optional, relative to this file: png, jpeg, ico or svg
label = "port"               # optional, the small label next to the name; "port" by default

# Optional: different program or arguments per system.
[linux]
command = "soh.appimage"

[windows]
command = "soh.exe"
args = []
```

Rules:

- `name` and `command` are required; everything else is optional. Unknown
  keys make Hanami ignore the file, so check spelling.
- Paths are relative to the file's folder; the game is started in that folder.
- Hanami only offers the game when the program exists. On Linux the program
  has to be executable.
- Keep it to one game per file.

## Your own Rust game

For a game you build yourself there is nothing to ship: with
`projects = ["~/Projects"]` in Hanami's settings, any Cargo package that
depends on a game engine and has a built program is offered. To name it, give
it an icon or arguments, add to its `Cargo.toml`:

```toml
[package.metadata.hanami]
name = "Sky Racer"
icon = "assets/icon.png"
args = ["--windowed"]
```

A package with this table is offered even without a known engine. See
GUIDE.md for how the program is chosen and where the game runs.
