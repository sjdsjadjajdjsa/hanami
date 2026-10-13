//! The list Hanami shows: games from settings plus every game found on the
//! computer, once each, and the search over it.

use std::collections::HashSet;
use std::path::PathBuf;

use crate::config::{Config, expand_home};

#[derive(Debug, Clone, PartialEq)]
pub enum Launch {
    Command {
        program: PathBuf,
        args: Vec<String>,
        dir: Option<PathBuf>,
    },
    /// A link a store app handles, like `steam://rungameid/730`.
    Open(String),
}

#[derive(Debug, Clone, PartialEq)]
pub struct Game {
    pub name: String,
    pub label: String,
    pub launch: Launch,
    /// A picture file for the row: png, jpeg, ico, svg, or (on Windows) an exe
    /// whose icon is used.
    pub icon: Option<PathBuf>,
}

/// Games from settings first, then the found ones; a name seen twice (in
/// any spelling, "Pixel Gun 3D: PC Edition" and "Pixel Gun 3D PC Edition")
/// keeps its first entry. Names in `hide` are left out. Sorted by name.
pub fn collect(config: &Config, found: Vec<Game>) -> Vec<Game> {
    let own = config.games.iter().map(|entry| Game {
        name: entry.name.clone(),
        label: entry.label.clone().unwrap_or_default(),
        launch: Launch::Command {
            program: expand_home(&entry.command),
            args: entry.args.clone(),
            dir: entry.dir.as_deref().map(expand_home),
        },
        icon: entry.icon.as_deref().map(expand_home),
    });
    let mut seen: HashSet<String> = config.hide.iter().map(|name| key(name)).collect();
    let mut games: Vec<Game> = own.chain(found).filter(|game| seen.insert(key(&game.name))).collect();
    for game in &mut games {
        if game.icon.is_none() {
            game.icon = exe_icon(&game.launch);
        }
    }
    games.sort_by_cached_key(|game| game.name.to_lowercase());
    games
}

/// On Windows, a program's own icon stands in when a game has no picture.
fn exe_icon(launch: &Launch) -> Option<PathBuf> {
    let Launch::Command { program, dir, .. } = launch else { return None };
    if !cfg!(windows) || !program.extension().is_some_and(|ext| ext.eq_ignore_ascii_case("exe")) {
        return None;
    }
    let exe = match (program.is_absolute(), dir) {
        (false, Some(dir)) => dir.join(program),
        _ => program.clone(),
    };
    Some(exe)
}

/// A name reduced to its letters and digits, for spotting the same game twice.
fn key(name: &str) -> String {
    name.chars().filter(|c| c.is_alphanumeric()).flat_map(char::to_lowercase).collect()
}

/// Positions in `games` whose names match `query`, best first: names that
/// start with it, then names with a word that starts with it, then names
/// that merely contain it. Ties keep alphabetical order.
pub fn filter(games: &[Game], query: &str) -> Vec<usize> {
    let query = query.trim().to_lowercase();
    if query.is_empty() {
        return (0..games.len()).collect();
    }
    let mut ranked: Vec<(u8, usize)> = games
        .iter()
        .enumerate()
        .filter_map(|(index, game)| {
            let name = game.name.to_lowercase();
            let rank = if name.starts_with(&query) {
                0
            } else if name.split(|c: char| !c.is_alphanumeric()).any(|word| word.starts_with(&query)) {
                1
            } else if name.contains(&query) {
                2
            } else {
                return None;
            };
            Some((rank, index))
        })
        .collect();
    ranked.sort();
    ranked.into_iter().map(|(_, index)| index).collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::{GameEntry, parse};

    fn names(games: &[Game], picked: &[usize]) -> Vec<String> {
        picked.iter().map(|&i| games[i].name.clone()).collect()
    }

    fn sample() -> Vec<Game> {
        let config = Config {
            games: ["Skate 3", "Pixel Gun 3D", "Rhythia"]
                .map(|name| GameEntry {
                    name: name.into(),
                    command: "x".into(),
                    args: vec![],
                    dir: None,
                    label: None,
                    icon: None,
                })
                .to_vec(),
            ..parse("").unwrap()
        };
        let found = [("Counter-Strike 2", 730), ("Outer Wilds", 1)]
            .map(|(name, id)| Game {
                name: name.into(),
                label: "steam".into(),
                launch: crate::find::steam_launch(id),
                icon: None,
            })
            .to_vec();
        collect(&config, found)
    }

    #[test]
    fn list_is_sorted_and_steam_games_are_labelled() {
        let games = sample();
        let all = filter(&games, "");
        assert_eq!(names(&games, &all), ["Counter-Strike 2", "Outer Wilds", "Pixel Gun 3D", "Rhythia", "Skate 3"]);
        assert_eq!(games[0].label, "steam");
        assert_eq!(games[0].launch, Launch::Open("steam://rungameid/730".into()));
    }

    #[test]
    fn search_ranks_starts_before_words_before_contains() {
        let games = sample();
        assert_eq!(names(&games, &filter(&games, "s")), ["Skate 3", "Counter-Strike 2", "Outer Wilds"]);
        assert_eq!(names(&games, &filter(&games, "GUN")), ["Pixel Gun 3D"]);
        assert!(filter(&games, "zelda").is_empty());
    }

    #[test]
    fn the_same_game_is_listed_once_and_hidden_games_not_at_all() {
        let found = |name: &str, label: &str| Game {
            name: name.into(),
            label: label.into(),
            launch: Launch::Open("x".into()),
            icon: None,
        };
        let mut config = parse("[[game]]\nname = \"Rhythia\"\ncommand = \"rhythia\"\nlabel = \"rust port\"\n").unwrap();
        config.hide = vec!["stardew valley".into()];
        let games = collect(
            &config,
            vec![
                found("Rhythia", "steam"),
                found("Pixel Gun 3D: PC Edition", "steam"),
                found("Pixel Gun 3D PC Edition", "app"),
                found("Stardew Valley", "steam"),
            ],
        );
        let listed: Vec<_> = games.iter().map(|g| (g.name.as_str(), g.label.as_str())).collect();
        assert_eq!(listed, [("Pixel Gun 3D: PC Edition", "steam"), ("Rhythia", "rust port")]);
    }

    #[test]
    fn exe_icons_stand_in_on_windows_only() {
        let command = |program: &str, dir: Option<&str>| Launch::Command {
            program: program.into(),
            args: vec![],
            dir: dir.map(PathBuf::from),
        };
        let expected = cfg!(windows).then(|| PathBuf::from(r"C:\Games\a.exe"));
        assert_eq!(exe_icon(&command(r"C:\Games\a.exe", None)), expected);
        if cfg!(windows) {
            assert_eq!(exe_icon(&command("a.EXE", Some(r"C:\Games"))), Some(PathBuf::from(r"C:\Games\a.EXE")));
        }
        assert_eq!(exe_icon(&command("lutris", None)), None);
        assert_eq!(exe_icon(&Launch::Open("steam://rungameid/1".into())), None);
    }

    #[test]
    fn home_in_commands_is_expanded() {
        let config = parse("[[game]]\nname = \"a\"\ncommand = \"~/bin/a\"\ndir = \"~/bin\"\n").unwrap();
        let home = dirs::home_dir().unwrap();
        let games = collect(&config, vec![]);
        assert_eq!(
            games[0].launch,
            Launch::Command { program: home.join("bin/a"), args: vec![], dir: Some(home.join("bin")) }
        );
    }
}
