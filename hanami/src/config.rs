//! The settings file: where it lives, what it holds, and turning it into
//! values Hanami can use.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use serde::Deserialize;
use toml_edit::{Array, ArrayOfTables, DocumentMut, InlineTable, Table, value};

use crate::find::Source;
use crate::games::key;

/// Written on first run, with a comment for every setting.
pub const DEFAULT: &str = r#"# Hanami settings. Changes show up the next time the panel opens.

# Key that opens and hides the panel, like "Ctrl+Alt+H" or "Super+H".
# Restart Hanami after changing it. On Wayland this built-in hotkey can't
# work: bind `hanami --toggle` in your desktop's shortcut settings instead.
hotkey = "Ctrl+Alt+H"

# What happens after a game starts: "hide", "keep" or "quit".
on_launch = "hide"

# Where Hanami looks for installed games. Remove one to stop looking there.
# Linux: steam, heroic (its Epic, GOG and Amazon games), lutris, and apps
# (games in your app menu). Windows: steam, epic, gog and heroic. Both:
# ports (game ports and rewrites, see folders and projects below).
find = ["steam", "heroic", "lutris", "apps", "epic", "gog", "ports"]

# Games shown at the top of the list, by name.
favourites = []

# Your own names for games, like { "Counter-Strike 2" = "CS2" }.
rename = {}

# Found games you don't want in the list, by name.
hide = []

# Extra folders to look in for game ports and rewrites (like Ship of
# Harkinian or Zelda 64: Recompiled) and for games that come with a
# hanami-game.toml file. ~/Games, ~/Downloads and a few other usual places
# are always searched.
folders = []

# Folders with your own Rust game projects, like ["~/Projects"]. Games
# built there (a program in target/release or target/debug of a project
# that uses a game engine) are offered in the panel.
projects = []

# Game controller: hold Start and Select together for half a second to open
# or hide the panel; in the panel, up and down move, A starts, B hides.
controller = true

# Hanami goes online at most once a day, only to GitHub: for the newest list
# of known ports and to check for a new version. false = never.
online = true

# Add your own games like this (remove the # signs):
#
# [[game]]
# name = "My Game"
# command = "~/Games/my-game/my-game"
# args = []
# dir = "~/Games/my-game"
# label = "my label"
# icon = "~/Games/my-game/icon.png"
#
# On Windows, put paths in single quotes so the backslashes stay as they are:
# command = 'C:\Games\My Game\game.exe'
"#;

#[derive(Debug, Clone, PartialEq, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Config {
    pub hotkey: String,
    pub on_launch: OnLaunch,
    pub find: Vec<Source>,
    pub favourites: Vec<String>,
    pub rename: BTreeMap<String, String>,
    pub hide: Vec<String>,
    pub folders: Vec<String>,
    pub projects: Vec<String>,
    pub controller: bool,
    pub online: bool,
    #[serde(rename = "game")]
    pub games: Vec<GameEntry>,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            hotkey: "Ctrl+Alt+H".into(),
            on_launch: OnLaunch::Hide,
            find: Source::ALL.to_vec(),
            favourites: Vec::new(),
            rename: BTreeMap::new(),
            hide: Vec::new(),
            folders: Vec::new(),
            projects: Vec::new(),
            controller: true,
            online: true,
            games: Vec::new(),
        }
    }
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum OnLaunch {
    #[default]
    Hide,
    Keep,
    Quit,
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct GameEntry {
    pub name: String,
    pub command: String,
    #[serde(default)]
    pub args: Vec<String>,
    pub dir: Option<String>,
    pub label: Option<String>,
    pub icon: Option<String>,
}

pub fn path() -> Option<PathBuf> {
    dirs::config_dir().map(|dir| dir.join("hanami").join("config.toml"))
}

/// Reads the settings file, writing the commented default first if there is none.
pub fn load(path: &Path) -> Result<Config, String> {
    if !path.exists() {
        if let Some(dir) = path.parent() {
            std::fs::create_dir_all(dir).map_err(|e| format!("Couldn't create the settings folder: {e}"))?;
        }
        std::fs::write(path, DEFAULT).map_err(|e| format!("Couldn't write the settings file: {e}"))?;
    }
    let text = std::fs::read_to_string(path).map_err(|e| format!("Couldn't read the settings file: {e}"))?;
    let mut config = parse(&text)?;
    // Settings written by 0.1 list every place there was; they get the new one too.
    if config.find == OLD_FIND {
        edit(path, |doc| add_name(doc, "find", "ports"))?;
        config.find.push(Source::Ports);
    }
    Ok(config)
}

const OLD_FIND: [Source; 6] = [Source::Steam, Source::Heroic, Source::Lutris, Source::Apps, Source::Epic, Source::Gog];

/// Changes the settings file in place, keeping its comments and layout.
/// A file with a mistake in it is left alone.
pub fn edit(path: &Path, change: impl FnOnce(&mut DocumentMut)) -> Result<(), String> {
    let text = std::fs::read_to_string(path).map_err(|e| format!("Couldn't read the settings file: {e}"))?;
    parse(&text)?;
    let mut doc: DocumentMut = text.parse().map_err(|e: toml_edit::TomlError| e.to_string())?;
    change(&mut doc);
    write_atomic(path, &doc.to_string())
}

/// Writes next to `path` first, so a crash never leaves half a file.
pub fn write_atomic(path: &Path, text: &str) -> Result<(), String> {
    let temp = path.with_extension("tmp");
    std::fs::write(&temp, text)
        .and_then(|()| std::fs::rename(&temp, path))
        .map_err(|e| format!("Couldn't save {}: {e}", path.display()))
}

fn list<'a>(doc: &'a mut DocumentMut, field: &str) -> &'a mut Array {
    if !doc.get(field).is_some_and(|item| item.is_array()) {
        doc[field] = value(Array::new());
    }
    doc[field].as_array_mut().expect("just made it a list")
}

/// Adds `name` to the list `field` (like favourites) unless it's there in any spelling.
pub fn add_name(doc: &mut DocumentMut, field: &str, name: &str) {
    let names = list(doc, field);
    if !names.iter().any(|item| item.as_str().is_some_and(|item| key(item) == key(name))) {
        names.push(name);
    }
}

pub fn remove_name(doc: &mut DocumentMut, field: &str, name: &str) {
    if let Some(names) = doc.get_mut(field).and_then(|item| item.as_array_mut()) {
        names.retain(|item| item.as_str().is_none_or(|item| key(item) != key(name)));
    }
}

/// Changes a game's name: an own game's `[[game]]` entry directly, a found
/// game through `rename`, from its `original` name.
pub fn rename(doc: &mut DocumentMut, original: &str, from: &str, to: &str) {
    if let Some(entry) = doc.get_mut("game").and_then(|item| item.as_array_of_tables_mut()).and_then(|games| {
        games.iter_mut().find(|game| game.get("name").and_then(|n| n.as_str()).is_some_and(|n| key(n) == key(from)))
    }) {
        entry["name"] = value(to);
    } else {
        if !doc.get("rename").is_some_and(|item| item.is_table_like()) {
            doc["rename"] = value(InlineTable::new());
        }
        let table = doc["rename"].as_table_like_mut().expect("just made it a table");
        let old: Vec<String> =
            table.iter().filter(|(name, _)| key(name) == key(original)).map(|(name, _)| name.to_owned()).collect();
        for name in old {
            table.remove(&name);
        }
        if key(original) != key(to) {
            table.insert(original, value(to));
        }
    }
    for field in ["favourites", "hide"] {
        if let Some(names) = doc.get_mut(field).and_then(|item| item.as_array_mut()) {
            for item in names.iter_mut() {
                if item.as_str().is_some_and(|name| key(name) == key(from)) {
                    *item = to.into();
                }
            }
        }
    }
}

/// Adds a `[[game]]` entry that runs `command` in `dir`.
pub fn add_game(doc: &mut DocumentMut, name: &str, command: &Path, dir: Option<&Path>) {
    if !doc.get("game").is_some_and(|item| item.is_array_of_tables()) {
        doc["game"] = toml_edit::Item::ArrayOfTables(ArrayOfTables::new());
    }
    let mut game = Table::new();
    game["name"] = value(name);
    game["command"] = value(command.to_string_lossy().as_ref());
    if let Some(dir) = dir {
        game["dir"] = value(dir.to_string_lossy().as_ref());
    }
    doc["game"].as_array_of_tables_mut().expect("just made it a list").push(game);
}

pub fn parse(text: &str) -> Result<Config, String> {
    toml::from_str(text).map_err(|error| {
        let line = error.span().map(|span| text[..span.start].lines().count().max(1));
        match line {
            Some(line) => format!("Settings, line {line}: {}", error.message()),
            None => format!("Settings: {}", error.message()),
        }
    })
}

/// `~/games/x` becomes the home folder plus `games/x`; anything else is kept.
pub fn expand_home(path: &str) -> PathBuf {
    match (path.strip_prefix("~/").or_else(|| path.strip_prefix("~\\")), dirs::home_dir()) {
        (Some(rest), Some(home)) => home.join(rest),
        _ => PathBuf::from(path),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_file_parses_to_default_settings() {
        assert_eq!(parse(DEFAULT), Ok(Config::default()));
    }

    #[test]
    fn games_and_choices_are_read() {
        let config = parse(
            "on_launch = \"keep\"\nfind = [\"steam\"]\n[[game]]\nname = \"Skate 3\"\ncommand = \"skate3\"\nlabel = \"rust port\"\n",
        )
        .unwrap();
        assert_eq!(config.on_launch, OnLaunch::Keep);
        assert_eq!(config.find, [Source::Steam]);
        assert!(parse("find = [\"origin\"]").is_err());
        assert_eq!(config.games[0].name, "Skate 3");
        assert!(config.games[0].args.is_empty());
    }

    #[test]
    fn mistakes_name_the_line() {
        let error = parse("hotkey = \"Ctrl+Alt+H\"\non_launch = \"later\"\n").unwrap_err();
        assert!(error.starts_with("Settings, line 2:"), "{error}");
        assert!(parse("[[game]]\nname = \"x\"\n").is_err());
    }

    #[test]
    fn edits_keep_comments_and_read_back() {
        let mut doc: DocumentMut = DEFAULT.parse().unwrap();
        add_name(&mut doc, "favourites", "Celeste");
        add_name(&mut doc, "favourites", "celeste");
        add_name(&mut doc, "hide", "Sober");
        rename(&mut doc, "Counter-Strike 2", "Counter-Strike 2", "CS2");
        rename(&mut doc, "Celeste", "Celeste", "Celeste Classic");
        add_game(&mut doc, "My Game", Path::new("/games/my game/run"), Some(Path::new("/games/my game")));
        rename(&mut doc, "My Game", "My Game", "Mine");
        remove_name(&mut doc, "hide", "SOBER");
        let text = doc.to_string();
        assert!(text.contains("# Games shown at the top of the list, by name."), "{text}");
        let config = parse(&text).unwrap();
        assert_eq!(config.favourites, ["Celeste Classic"]);
        assert!(config.hide.is_empty());
        assert_eq!(config.rename.get("Counter-Strike 2").map(String::as_str), Some("CS2"));
        assert_eq!(config.rename.get("Celeste").map(String::as_str), Some("Celeste Classic"));
        assert_eq!(config.games[0].name, "Mine");
        assert_eq!(config.games[0].dir.as_deref(), Some("/games/my game"));
        assert!(!config.rename.contains_key("My Game"));
    }

    #[test]
    fn old_settings_get_the_ports_finder() {
        let dir = std::env::temp_dir().join(format!("hanami-config-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("config.toml");
        std::fs::write(&path, "# mine\nfind = [\"steam\", \"heroic\", \"lutris\", \"apps\", \"epic\", \"gog\"]\n")
            .unwrap();
        assert_eq!(load(&path).unwrap().find, Source::ALL);
        assert!(std::fs::read_to_string(&path).unwrap().starts_with("# mine\n"));
        assert_eq!(parse(&std::fs::read_to_string(&path).unwrap()).unwrap().find, Source::ALL);
        std::fs::write(&path, "find = [\"steam\"]\n").unwrap();
        assert_eq!(load(&path).unwrap().find, [Source::Steam]);
        std::fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn home_is_expanded_only_at_the_start() {
        let home = dirs::home_dir().unwrap();
        assert_eq!(expand_home("~/a/b"), home.join("a/b"));
        assert_eq!(expand_home("/usr/bin/x"), PathBuf::from("/usr/bin/x"));
        assert_eq!(expand_home("a~/b"), PathBuf::from("a~/b"));
        assert_eq!(expand_home("~\\a"), home.join("a"));
    }
}
