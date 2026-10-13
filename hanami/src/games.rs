//! The list Hanami shows: games from settings plus every game found on the
//! computer, once each, and the search over it.

use std::cmp::Reverse;
use std::collections::{BTreeMap, HashMap, HashSet};
use std::path::{Path, PathBuf};

use nucleo_matcher::pattern::{AtomKind, CaseMatching, Normalization, Pattern};
use nucleo_matcher::{Matcher, Utf32Str};

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
    /// A picture file for the row: png, jpeg, ico or svg.
    pub icon: Option<PathBuf>,
}

/// Games from settings first, then the found ones, each under its name from
/// `rename`; a name seen twice (in any spelling, "Pixel Gun 3D: PC Edition"
/// and "Pixel Gun 3D PC Edition") keeps its first entry. Names in `hide`,
/// old or new, are left out. Sorted by name.
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
    let renames: HashMap<String, &str> = config.rename.iter().map(|(from, to)| (key(from), to.as_str())).collect();
    let hidden: HashSet<String> = config.hide.iter().map(|name| key(name)).collect();
    let mut seen = HashSet::new();
    let mut games: Vec<Game> = own
        .chain(found)
        .filter_map(|mut game| {
            let original = key(&game.name);
            if let Some(name) = renames.get(&original) {
                game.name = (*name).to_owned();
            }
            let shown = key(&game.name);
            (!hidden.contains(&original) && !hidden.contains(&shown) && seen.insert(shown)).then_some(game)
        })
        .collect();
    games.sort_by_cached_key(|game| game.name.to_lowercase());
    games
}

/// The name a game had before `rename` gave it `name`.
pub fn original_name<'a>(config: &'a Config, name: &'a str) -> &'a str {
    config.rename.iter().find(|(_, to)| key(to) == key(name)).map_or(name, |(from, _)| from.as_str())
}

/// A name from a program's file name: "hollow_knight.x86_64" becomes
/// "Hollow Knight".
pub fn readable(program: &Path) -> String {
    let stem = program.file_stem().map(|stem| stem.to_string_lossy().into_owned()).unwrap_or_default();
    let words: Vec<String> = stem
        .split(['_', '-', ' ', '.'])
        .filter(|word| !word.is_empty())
        .map(|word| {
            let mut letters = word.chars();
            match letters.next() {
                Some(first) if !word.chars().any(char::is_uppercase) => first.to_uppercase().chain(letters).collect(),
                _ => word.to_owned(),
            }
        })
        .collect();
    if words.is_empty() { "New game".into() } else { words.join(" ") }
}

/// A name reduced to its letters and digits, for spotting the same game twice.
pub fn key(name: &str) -> String {
    name.chars().filter(|c| c.is_alphanumeric()).flat_map(char::to_lowercase).collect()
}

/// New finds first, then favourites by name, then games by when they were
/// last played, then everything else by name.
pub fn order(games: &mut [Game], new: &HashSet<String>, favourites: &[String], played: &BTreeMap<String, u64>) {
    let favourites: HashSet<String> = favourites.iter().map(|name| key(name)).collect();
    games.sort_by_cached_key(|game| {
        let name = key(&game.name);
        let (group, last) = if new.contains(&name) {
            (0, 0)
        } else if favourites.contains(&name) {
            (1, 0)
        } else if let Some(&time) = played.get(&name) {
            (2, time)
        } else {
            (3, 0)
        };
        (group, Reverse(last), game.name.to_lowercase())
    });
}

/// Positions in `games` whose names match `query`, best first: names that
/// start with it, then names with a word that starts with it, then names
/// whose initials start with it ("hk" for Hollow Knight), then names that
/// merely contain it. Ties keep the list's order. Only when none of those
/// match, it allows for missing letters and small typos.
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
            let words = words(&name);
            let initials: String = words.iter().filter_map(|word| word.chars().next()).collect();
            let rank = if name.starts_with(&query) {
                0
            } else if words.iter().any(|word| word.starts_with(&query)) {
                1
            } else if query.chars().count() > 1 && initials.starts_with(&query) {
                2
            } else if name.contains(&query) {
                3
            } else {
                return None;
            };
            Some((rank, index))
        })
        .collect();
    if ranked.is_empty() {
        return forgiving(games, &query);
    }
    ranked.sort();
    ranked.into_iter().map(|(_, index)| index).collect()
}

fn words(name: &str) -> Vec<&str> {
    name.split(|c: char| !c.is_alphanumeric()).filter(|word| !word.is_empty()).collect()
}

/// Names with the query's letters in order ("holow" for Hollow Knight), best
/// match first, then names with a word one or two typos away.
fn forgiving(games: &[Game], query: &str) -> Vec<usize> {
    let length = query.chars().count();
    if length < 3 {
        return Vec::new();
    }
    let pattern = Pattern::new(query, CaseMatching::Ignore, Normalization::Smart, AtomKind::Fuzzy);
    let mut matcher = Matcher::new(nucleo_matcher::Config::DEFAULT);
    let mut buffer = Vec::new();
    let typos = if length >= 6 { 2 } else { 1 };
    let mut ranked: Vec<(u8, Reverse<u32>, usize)> = games
        .iter()
        .enumerate()
        .filter_map(|(index, game)| {
            if let Some(score) = pattern.score(Utf32Str::new(&game.name, &mut buffer), &mut matcher) {
                return Some((0, Reverse(score), index));
            }
            let name = game.name.to_lowercase();
            let close = words(&name).iter().any(|word| {
                let start: String = word.chars().take(length).collect();
                strsim::damerau_levenshtein(query, &start).min(strsim::damerau_levenshtein(query, word)) <= typos
            });
            close.then_some((1, Reverse(0), index))
        })
        .collect();
    ranked.sort();
    ranked.into_iter().map(|(_, _, index)| index).collect()
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
    fn initials_typos_and_missing_letters_still_find_games() {
        let found =
            |name: &str| Game { name: name.into(), label: String::new(), launch: Launch::Open("x".into()), icon: None };
        let games: Vec<Game> =
            ["Counter-Strike 2", "Hollow Knight", "Stardew Valley", "Hades", "Shovel Knight"].map(found).to_vec();
        assert_eq!(names(&games, &filter(&games, "hk")), ["Hollow Knight"]);
        assert_eq!(names(&games, &filter(&games, "cs2")), ["Counter-Strike 2"]);
        assert_eq!(names(&games, &filter(&games, "holow")), ["Hollow Knight"]);
        assert_eq!(names(&games, &filter(&games, "stradew")), ["Stardew Valley"]);
        assert_eq!(names(&games, &filter(&games, "knight")), ["Hollow Knight", "Shovel Knight"]);
        assert!(filter(&games, "zz").is_empty());
        assert!(filter(&games, "minecraft").is_empty());
    }

    #[test]
    fn new_then_favourites_then_recent_then_the_rest() {
        let found =
            |name: &str| Game { name: name.into(), label: String::new(), launch: Launch::Open("x".into()), icon: None };
        let mut games: Vec<Game> =
            ["Celeste", "Hades", "Outer Wilds", "Sober", "Stardew Valley", "Tunic"].map(found).to_vec();
        let new = HashSet::from([key("Tunic")]);
        let played = BTreeMap::from([(key("Celeste"), 10), (key("Sober"), 30), (key("Hades"), 20)]);
        order(&mut games, &new, &["stardew valley".into(), "Hades".into()], &played);
        let listed: Vec<_> = games.iter().map(|game| game.name.as_str()).collect();
        assert_eq!(listed, ["Tunic", "Hades", "Stardew Valley", "Sober", "Celeste", "Outer Wilds"]);
    }

    #[test]
    fn renamed_games_show_their_new_name_and_hide_by_either() {
        let found = |name: &str| Game {
            name: name.into(),
            label: "steam".into(),
            launch: Launch::Open("x".into()),
            icon: None,
        };
        let mut config = parse("rename = { \"Counter-Strike 2\" = \"CS2\", \"Hades\" = \"Hades I\" }\n").unwrap();
        config.hide = vec!["Hades I".into()];
        let games = collect(&config, vec![found("Counter-Strike 2"), found("Hades"), found("Celeste")]);
        let listed: Vec<_> = games.iter().map(|game| game.name.as_str()).collect();
        assert_eq!(listed, ["Celeste", "CS2"]);
        assert_eq!(original_name(&config, "cs2"), "Counter-Strike 2");
        assert_eq!(original_name(&config, "Celeste"), "Celeste");
    }

    #[test]
    fn program_files_give_readable_names() {
        assert_eq!(readable(Path::new("/games/hollow_knight.x86_64")), "Hollow Knight");
        assert_eq!(readable(Path::new("C:/Games/Celeste/Celeste.exe")), "Celeste");
        assert_eq!(readable(Path::new("/a/SoH-MacReady-Linux.AppImage")), "SoH MacReady Linux");
        assert_eq!(readable(Path::new("/a/.x")), "X");
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
