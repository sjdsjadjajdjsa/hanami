# Packaging

How Hanami's downloads are made. The release workflow
(`.github/workflows/release.yml`) runs all of this when a tag like `v0.2.0`
is pushed; the tag must match `version` in `hanami/Cargo.toml`.

| Asset | Made by |
|---|---|
| `hanami-linux-x86_64.tar.gz` | the workflow: binary, README, GUIDE, LICENSE |
| `hanami-x86_64.AppImage` | `linux/appimage.sh` with appimagetool |
| `hanami-windows-x86_64.zip` | the workflow: exe, README, GUIDE, LICENSE |
| `hanami-setup-x86_64.exe` | `windows/hanami.iss` with Inno Setup 6 (`iscc`, on the GitHub Windows runners) |
| AUR `hanami-bin` | `aur/hanami-bin/`, published by hand (below) |

## Linux: AppImage

`linux/appimage.sh target/release/hanami` builds `hanami-x86_64.AppImage`
from the binary, `linux/hanami.desktop` and `assets/hanami-icon.svg`. It
downloads appimagetool (github.com/AppImage/appimagetool, continuous build)
unless `APPIMAGETOOL` points at one. Only the Hanami binary is inside: it
needs glibc 2.39 or newer (Ubuntu 24.04 and anything from 2024 on) and
fontconfig, which every desktop has.

The desktop file is in `Game;Utility;`, so Hanami's own app-menu search
leaves it out even when an AppImage tool installs it under another name.

## Windows: installer

`windows/hanami.iss` is an Inno Setup 6 script:

- per user (`PrivilegesRequired=lowest`), into `%LOCALAPPDATA%\Programs\Hanami`
- Start menu shortcut, optional desktop shortcut
- a task "Start Hanami when Windows starts", off unless ticked, that writes
  `"...\hanami.exe" --hidden` to `HKCU\...\CurrentVersion\Run`; running the
  installer again with the box unticked removes it
- uninstall first asks a running Hanami to close (`hanami.exe --quit`),
  then removes the program, shortcuts, the Run entry and
  `%LOCALAPPDATA%\hanami` (the update stamp); settings in `%APPDATA%\hanami`
  stay

Build: `iscc /DVersion=0.2.0 /DSource=C:\path\to\dist\hanami packaging\windows\hanami.iss`
(Source is a folder with hanami.exe, README.md, GUIDE.md and LICENSE).
On Linux it also compiles under Wine after installing Inno Setup there
(`wine innosetup-6.x.exe /VERYSILENT`, then `wine .../ISCC.exe ...`).

`windows/hanami.ico` was made from `assets/hanami-icon.svg` with
`rsvg-convert` at 16 to 256 px, stored as PNG frames.

## Arch Linux: AUR

`aur/hanami-bin/` holds the `PKGBUILD`, `.SRCINFO` and `hanami.desktop`
for the `hanami-bin` package: it installs the released binary, the desktop
file, the icon and the licence. The names `hanami` and `hanami-bin` were free
on aur.archlinux.org in October 2026.

### Publishing for the first time

1. Make an account at <https://aur.archlinux.org/register>.
2. Make an SSH key just for the AUR and add the public half in your AUR
   account page under "SSH Public Key":

       ssh-keygen -t ed25519 -f ~/.ssh/aur -C aur
       cat ~/.ssh/aur.pub

   Tell SSH to use it, in `~/.ssh/config`:

       Host aur.archlinux.org
         IdentityFile ~/.ssh/aur
         User aur

3. Clone the (empty) package repository. The clone creates the package name:

       git clone ssh://aur@aur.archlinux.org/hanami-bin.git
       cd hanami-bin

4. Copy `PKGBUILD`, `.SRCINFO` and `hanami.desktop` from
   `packaging/aur/hanami-bin/` into it, check them, then push:

       makepkg --printsrcinfo > .SRCINFO
       git add PKGBUILD .SRCINFO hanami.desktop
       git commit -m "hanami-bin 0.2.0-1"
       git push origin master

   The AUR accepts only the `master` branch and refuses pushes where
   `.SRCINFO` is missing or out of date.

### Every release after that

1. In `PKGBUILD`, set `pkgver` to the new version, `pkgrel=1`, and replace
   the first two `sha256sums` with the sums of the new tar.gz and icon:

       curl -sL https://github.com/sjdsjadjajdjsa/hanami/releases/download/v0.2.0/hanami-linux-x86_64.tar.gz | sha256sum
       curl -sL https://raw.githubusercontent.com/sjdsjadjajdjsa/hanami/v0.2.0/assets/hanami-icon.svg | sha256sum

   (`updpkgsums` from `pacman-contrib` does this for you.) If
   `hanami.desktop` changed, copy the new one and update its sum too.
2. Check it builds: `makepkg -f` in that folder, and `namcap PKGBUILD
   *.pkg.tar.zst` if namcap is installed.
3. `makepkg --printsrcinfo > .SRCINFO`, commit both files with the new
   version as the message, push to the AUR repository, and copy the files
   back into `packaging/aur/hanami-bin/` in this repository.
