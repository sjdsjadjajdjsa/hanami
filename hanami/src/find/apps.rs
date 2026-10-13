//! Games in the Linux app menu: desktop entries in the "Game" category.

use std::collections::HashSet;
use std::path::{Path, PathBuf};

use super::icon_theme::Lookup as IconTheme;
use crate::games::{Game, Launch};

/// Launchers that list games themselves; their games are found directly.
const LAUNCHERS: [&str; 7] = [
    "steam.desktop",
    "com.valvesoftware.Steam.desktop",
    "heroic.desktop",
    "com.heroicgameslauncher.hgl.desktop",
    "lutris.desktop",
    "net.lutris.Lutris.desktop",
    "hanami.desktop",
];

pub fn find() -> Vec<Game> {
    let mut seen = HashSet::new();
    let mut games = Vec::new();
    let icons = IconTheme::new(&icon_theme(), 48);
    for dir in dirs() {
        let mut files = Vec::new();
        collect_files(&dir, &mut files);
        for file in files {
            let Some(id) = desktop_id(&dir, &file) else { continue };
            // The first file with an id wins, in data-dir order.
            if !seen.insert(id.clone()) {
                continue;
            }
            let Ok(text) = std::fs::read_to_string(&file) else { continue };
            if let Some(mut game) = parse(&text).and_then(|entry| entry.into_game(&id, &file)) {
                game.icon = game.icon.take().and_then(|icon| icon_path(&icon, &icons));
                games.push(game);
            }
        }
    }
    games
}

/// Application folders in freedesktop order, plus Flatpak's exports, which
/// sessions started outside a login shell may not have in `XDG_DATA_DIRS`.
fn dirs() -> Vec<PathBuf> {
    let home = dirs::home_dir().unwrap_or_default();
    let data_home = std::env::var_os("XDG_DATA_HOME")
        .filter(|v| !v.is_empty())
        .map(PathBuf::from)
        .unwrap_or_else(|| home.join(".local/share"));
    let data_dirs = std::env::var("XDG_DATA_DIRS")
        .ok()
        .filter(|v| !v.is_empty())
        .unwrap_or_else(|| "/usr/local/share:/usr/share".into());
    let mut roots = vec![data_home];
    roots.extend(data_dirs.split(':').filter(|d| !d.is_empty()).map(PathBuf::from));
    roots.push(home.join(".local/share/flatpak/exports/share"));
    roots.push(PathBuf::from("/var/lib/flatpak/exports/share"));
    let mut seen = HashSet::new();
    roots.into_iter().map(|root| root.join("applications")).filter(|dir| seen.insert(dir.clone())).collect()
}

fn collect_files(dir: &Path, out: &mut Vec<PathBuf>) {
    let Ok(entries) = std::fs::read_dir(dir) else { return };
    let mut entries: Vec<_> = entries.flatten().map(|e| e.path()).collect();
    entries.sort();
    for path in entries {
        if path.is_dir() {
            collect_files(&path, out);
        } else if path.extension().is_some_and(|ext| ext == "desktop") {
            out.push(path);
        }
    }
}

/// `games/foo.desktop` under an applications folder has the id `games-foo.desktop`.
fn desktop_id(dir: &Path, file: &Path) -> Option<String> {
    let relative = file.strip_prefix(dir).ok()?;
    Some(relative.to_string_lossy().replace('/', "-"))
}

#[derive(Debug, Default, PartialEq)]
struct Entry {
    name: String,
    exec: String,
    path: Option<String>,
    icon: Option<String>,
    is_application: bool,
    is_game: bool,
    hidden: bool,
}

/// Reads the `[Desktop Entry]` group; other groups (actions) are ignored.
fn parse(text: &str) -> Option<Entry> {
    let mut entry = Entry::default();
    let mut in_main = false;
    for line in text.lines().map(str::trim) {
        if line.starts_with('[') {
            in_main = line == "[Desktop Entry]";
            continue;
        }
        if !in_main || line.starts_with('#') {
            continue;
        }
        let Some((key, value)) = line.split_once('=') else { continue };
        let value = value.trim();
        match key.trim() {
            "Name" => entry.name = value.to_string(),
            "Exec" => entry.exec = value.to_string(),
            "Path" if !value.is_empty() => entry.path = Some(value.to_string()),
            "Icon" if !value.is_empty() => entry.icon = Some(value.to_string()),
            "Type" => entry.is_application = value == "Application",
            // Game tools (Proton managers and the like) are also "Utility".
            "Categories" => {
                let categories: Vec<&str> = value.split(';').collect();
                entry.is_game = categories.contains(&"Game") && !categories.contains(&"Utility");
            }
            "NoDisplay" | "Hidden" if value == "true" => entry.hidden = true,
            _ => {}
        }
    }
    (!entry.name.is_empty() && !entry.exec.is_empty()).then_some(entry)
}

impl Entry {
    fn into_game(self, id: &str, file: &Path) -> Option<Game> {
        if !self.is_application || !self.is_game || self.hidden || LAUNCHERS.contains(&id) {
            return None;
        }
        let args = exec_args(&self.exec, &self.name, file)?;
        // The icon is still the `Icon=` value here; `find` resolves names to files.
        let icon = self.icon.map(PathBuf::from);
        // Steam's own shortcuts launch through Steam, like the Steam source does.
        if let Some(url) = args.iter().find(|arg| arg.starts_with("steam://rungameid/")) {
            return Some(Game { name: self.name, label: "steam".into(), launch: Launch::Open(url.clone()), icon });
        }
        let (program, args) = args.split_first()?;
        Some(Game {
            name: self.name,
            label: "app".into(),
            launch: Launch::Command {
                program: PathBuf::from(program),
                args: args.to_vec(),
                dir: self.path.map(PathBuf::from),
            },
            icon,
        })
    }
}

/// An `Icon=` value as a file: absolute paths as they are, names looked up
/// in the icon theme (and hicolor behind it).
fn icon_path(icon: &Path, theme: &IconTheme) -> Option<PathBuf> {
    if icon.is_absolute() {
        return icon.is_file().then(|| icon.to_path_buf());
    }
    // Some entries name the file rather than the icon.
    let name = icon.to_str()?;
    let name = match name.rsplit_once('.') {
        Some((stem, "png" | "svg" | "xpm")) => stem,
        _ => name,
    };
    theme.find(name)
}

/// The user's icon theme: KDE's setting, then GTK's, then plain hicolor.
fn icon_theme() -> String {
    let config = dirs::config_dir().unwrap_or_default();
    [
        (config.join("kdeglobals"), "[Icons]", "Theme="),
        (config.join("kdedefaults/kdeglobals"), "[Icons]", "Theme="),
        (PathBuf::from("/etc/xdg/kdeglobals"), "[Icons]", "Theme="),
        (config.join("gtk-4.0/settings.ini"), "[Settings]", "gtk-icon-theme-name="),
        (config.join("gtk-3.0/settings.ini"), "[Settings]", "gtk-icon-theme-name="),
    ]
    .iter()
    .filter_map(|(path, group, key)| std::fs::read_to_string(path).ok().map(|text| (text, *group, *key)))
    .find_map(|(text, group, key)| ini_value(&text, group, key))
    .unwrap_or_else(|| "hicolor".into())
}

/// `key` in `group` of an ini-style settings file, like kdeglobals.
fn ini_value(text: &str, group: &str, key: &str) -> Option<String> {
    let mut inside = false;
    for line in text.lines().map(str::trim) {
        if line.starts_with('[') {
            inside = line == group;
        } else if inside && let Some(value) = line.strip_prefix(key) {
            return Some(value.trim().to_string()).filter(|v| !v.is_empty());
        }
    }
    None
}

/// Splits an `Exec` value into arguments: undoes the string escapes and the
/// double-quote rules, and drops field codes, since nothing is being opened.
fn exec_args(exec: &str, name: &str, file: &Path) -> Option<Vec<String>> {
    let unescaped = unescape_string(exec);
    let mut words: Vec<(String, bool)> = Vec::new();
    let mut chars = unescaped.chars().peekable();
    while let Some(&c) = chars.peek() {
        if c.is_whitespace() {
            chars.next();
            continue;
        }
        let mut word = String::new();
        let mut quoted = false;
        if c == '"' {
            quoted = true;
            chars.next();
            loop {
                match chars.next()? {
                    '"' => break,
                    '\\' => word.push(chars.next()?),
                    other => word.push(other),
                }
            }
        } else {
            while let Some(&c) = chars.peek() {
                if c.is_whitespace() {
                    break;
                }
                word.push(c);
                chars.next();
            }
        }
        words.push((word, quoted));
    }

    let mut args = Vec::new();
    for (word, quoted) in words {
        if !quoted {
            match word.as_str() {
                "%f" | "%F" | "%u" | "%U" | "%i" | "%d" | "%D" | "%n" | "%N" | "%v" | "%m" => continue,
                "%c" => {
                    args.push(name.to_string());
                    continue;
                }
                "%k" => {
                    args.push(file.to_string_lossy().into_owned());
                    continue;
                }
                // Flatpak wraps file arguments in these markers.
                "@@" | "@@u" | "@@f" => continue,
                _ => {}
            }
        }
        args.push(word.replace("%%", "%"));
    }
    (!args.is_empty()).then_some(args)
}

/// Desktop files escape `\s`, `\n`, `\t`, `\r` and `\\` in string values.
fn unescape_string(value: &str) -> String {
    let mut out = String::with_capacity(value.len());
    let mut chars = value.chars();
    while let Some(c) = chars.next() {
        if c != '\\' {
            out.push(c);
            continue;
        }
        match chars.next() {
            Some('s') => out.push(' '),
            Some('n') => out.push('\n'),
            Some('t') => out.push('\t'),
            Some('r') => out.push('\r'),
            Some('\\') => out.push('\\'),
            Some(other) => {
                out.push('\\');
                out.push(other);
            }
            None => out.push('\\'),
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn args(exec: &str) -> Vec<String> {
        exec_args(exec, "Game", Path::new("/a/game.desktop")).unwrap()
    }

    #[test]
    fn exec_quotes_escapes_and_field_codes() {
        assert_eq!(args("prismlauncher %U"), ["prismlauncher"]);
        assert_eq!(args(r#""/opt/My Game/run" --mode "a \"b\"" %f"#), ["/opt/My Game/run", "--mode", "a \"b\""]);
        assert_eq!(args("game --progress=50%% %i"), ["game", "--progress=50%"]);
        assert_eq!(
            args("/usr/bin/flatpak run --branch=stable --command=sh org.x.Game @@u %U @@"),
            ["/usr/bin/flatpak", "run", "--branch=stable", "--command=sh", "org.x.Game"]
        );
        assert_eq!(args(r#""C:\\\\Games\\\\x.exe""#), [r"C:\Games\x.exe"]);
        assert!(exec_args("\"unterminated", "x", Path::new("x")).is_none());
    }

    #[test]
    fn only_shown_games_are_kept() {
        let game = "[Desktop Entry]\nType=Application\nName=Rhythia\nExec=rhythia\nCategories=Game;\n";
        let entry = parse(game).unwrap();
        let found = entry.into_game("rhythia.desktop", Path::new("x")).unwrap();
        assert_eq!(found.name, "Rhythia");
        assert_eq!(found.label, "app");
        assert_eq!(found.icon, None);
        assert_eq!(found.launch, Launch::Command { program: "rhythia".into(), args: vec![], dir: None });

        let not_game = "[Desktop Entry]\nType=Application\nName=Editor\nExec=ed\nCategories=Utility;\n";
        assert!(parse(not_game).unwrap().into_game("ed.desktop", Path::new("x")).is_none());
        let hidden = format!("{game}NoDisplay=true\n");
        assert!(parse(&hidden).unwrap().into_game("r.desktop", Path::new("x")).is_none());
        assert!(parse(game).unwrap().into_game("steam.desktop", Path::new("x")).is_none());
        let tool = "[Desktop Entry]\nType=Application\nName=ProtonUp-Qt\nExec=pupgui2\nCategories=Game;Utility;\n";
        assert!(parse(tool).unwrap().into_game("net.davidotek.pupgui2.desktop", Path::new("x")).is_none());
    }

    #[test]
    fn actions_do_not_override_the_main_entry() {
        let text = "[Desktop Entry]\nType=Application\nName=Game\nExec=game\nCategories=Game;\n\n[Desktop Action safe]\nName=Safe mode\nExec=game --safe\n";
        let entry = parse(text).unwrap();
        assert_eq!((entry.name.as_str(), entry.exec.as_str()), ("Game", "game"));
    }

    #[test]
    fn steam_shortcuts_launch_through_steam() {
        let text = "[Desktop Entry]\nType=Application\nName=Stardew Valley\nExec=steam steam://rungameid/413150\nCategories=Game;\n";
        let game = parse(text).unwrap().into_game("Stardew Valley.desktop", Path::new("x")).unwrap();
        assert_eq!(game.launch, Launch::Open("steam://rungameid/413150".into()));
        assert_eq!(game.label, "steam");
    }

    #[test]
    fn ids_and_first_file_wins() {
        let root = std::env::temp_dir().join(format!("hanami-apps-{}", std::process::id()));
        let (first, second) = (root.join("one/applications"), root.join("two/applications/games"));
        std::fs::create_dir_all(&first).unwrap();
        std::fs::create_dir_all(&second).unwrap();
        assert_eq!(desktop_id(&root.join("two/applications"), &second.join("x.desktop")).unwrap(), "games-x.desktop");
        let mut files = Vec::new();
        std::fs::write(first.join("a.desktop"), "").unwrap();
        std::fs::write(second.join("b.desktop"), "").unwrap();
        std::fs::write(second.join("notes.txt"), "").unwrap();
        collect_files(&root, &mut files);
        assert_eq!(files.len(), 2);
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn icons_absolute_or_looked_up_in_the_theme() {
        let text = "[Desktop Entry]\nType=Application\nName=Game\nExec=game\nIcon=my-game.png\nCategories=Game;\n";
        let game = parse(text).unwrap().into_game("g.desktop", Path::new("x")).unwrap();
        assert_eq!(game.icon, Some(PathBuf::from("my-game.png")));

        let root = std::env::temp_dir().join(format!("hanami-icons-{}", std::process::id()));
        std::fs::create_dir_all(&root).unwrap();
        let file = root.join("icon.png");
        std::fs::write(&file, "").unwrap();
        let theme = IconTheme::new("hicolor", 48);
        assert_eq!(icon_path(&file, &theme), Some(file));
        assert_eq!(icon_path(&root.join("missing.png"), &theme), None);
        assert_eq!(icon_path(Path::new("hanami-no-such-icon-anywhere"), &theme), None);
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn kde_theme_is_read_from_the_icons_group() {
        let kde = |text| ini_value(text, "[Icons]", "Theme=");
        assert_eq!(kde("[General]\nTheme=x\n\n[Icons]\nTheme=breeze-dark\n"), Some("breeze-dark".into()));
        assert_eq!(kde("[Icons]\nTheme=\n"), None);
        assert_eq!(kde("[General]\nTheme=x\n"), None);
        assert_eq!(
            ini_value("[Settings]\ngtk-icon-theme-name=Papirus\n", "[Settings]", "gtk-icon-theme-name="),
            Some("Papirus".into())
        );
    }
}
