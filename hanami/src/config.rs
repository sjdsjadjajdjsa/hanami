//! The settings file: where it lives, what it holds, and turning it into
//! values Hanami can use.

use std::path::{Path, PathBuf};

use serde::Deserialize;

use crate::find::Source;

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
# (games in your app menu). Windows: steam, epic, gog and heroic.
find = ["steam", "heroic", "lutris", "apps", "epic", "gog"]

# Found games you don't want in the list, by name.
hide = []

# Add your own games like this (remove the # signs):
#
# [[game]]
# name = "My Game"
# command = "~/Games/my-game/my-game"
# args = []
# dir = "~/Games/my-game"
# label = "my label"
"#;

#[derive(Debug, Clone, PartialEq, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Config {
    pub hotkey: String,
    pub on_launch: OnLaunch,
    pub find: Vec<Source>,
    pub hide: Vec<String>,
    #[serde(rename = "game")]
    pub games: Vec<GameEntry>,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            hotkey: "Ctrl+Alt+H".into(),
            on_launch: OnLaunch::Hide,
            find: Source::ALL.to_vec(),
            hide: Vec::new(),
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
    parse(&text)
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
    match (path.strip_prefix("~/"), dirs::home_dir()) {
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
    fn home_is_expanded_only_at_the_start() {
        let home = dirs::home_dir().unwrap();
        assert_eq!(expand_home("~/a/b"), home.join("a/b"));
        assert_eq!(expand_home("/usr/bin/x"), PathBuf::from("/usr/bin/x"));
        assert_eq!(expand_home("a~/b"), PathBuf::from("a~/b"));
    }
}
