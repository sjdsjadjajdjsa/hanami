//! Games installed through Heroic: Epic (legendary), GOG, Amazon (nile) and
//! programs added by hand ("sideloaded"). Heroic launches them itself.

use std::collections::HashMap;
use std::path::{Path, PathBuf};

use serde_json::Value;

use crate::games::{Game, Launch};

const FLATPAK_ID: &str = "com.heroicgameslauncher.hgl";

pub fn find() -> Vec<Game> {
    let mut games = Vec::new();
    for (root, flatpak) in roots() {
        if root.is_dir() {
            games.extend(installed(&root).into_iter().map(|found| found.into_game(flatpak)));
        }
    }
    games
}

/// Heroic's settings folder, native and (on Linux) Flatpak.
fn roots() -> Vec<(PathBuf, bool)> {
    let mut roots: Vec<(PathBuf, bool)> = dirs::config_dir().map(|dir| (dir.join("heroic"), false)).into_iter().collect();
    if cfg!(target_os = "linux")
        && let Some(home) = dirs::home_dir()
    {
        roots.push((home.join(".var/app").join(FLATPAK_ID).join("config/heroic"), true));
    }
    roots
}

#[derive(Debug, PartialEq)]
struct Found {
    name: String,
    app: String,
    runner: &'static str,
    label: &'static str,
}

impl Found {
    fn into_game(self, flatpak: bool) -> Game {
        let url = format!("heroic://launch?appName={}&runner={}", super::encode(&self.app), self.runner);
        let launch = if flatpak {
            Launch::Command { program: "flatpak".into(), args: vec!["run".into(), FLATPAK_ID.into(), url], dir: None }
        } else {
            Launch::Open(url)
        };
        Game { name: self.name, label: self.label.into(), launch, icon: None }
    }
}

fn read(path: &Path) -> Value {
    std::fs::read_to_string(path)
        .ok()
        .and_then(|text| serde_json::from_str(&text).ok())
        .unwrap_or(Value::Null)
}

fn text<'a>(value: &'a Value, key: &str) -> Option<&'a str> {
    value.get(key)?.as_str().filter(|s| !s.is_empty())
}

fn installed(root: &Path) -> Vec<Found> {
    let mut found = Vec::new();

    // Epic: an object keyed by app name, with titles.
    if let Value::Object(games) = read(&root.join("legendaryConfig/legendary/installed.json")) {
        for game in games.values() {
            if game.get("is_dlc").and_then(Value::as_bool) == Some(true) {
                continue;
            }
            if let (Some(app), Some(title)) = (text(game, "app_name"), text(game, "title")) {
                found.push(Found { name: title.into(), app: app.into(), runner: "legendary", label: "epic" });
            }
        }
    }

    // GOG: installed ids here, titles in the library cache.
    let titles: HashMap<String, String> = read(&root.join("store_cache/gog_library.json"))
        .get("games")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|game| Some((text(game, "app_name")?.to_string(), text(game, "title")?.to_string())))
        .collect();
    for game in read(&root.join("gog_store/installed.json")).get("installed").and_then(Value::as_array).into_iter().flatten() {
        let Some(app) = text(game, "appName") else { continue };
        if app == "gog-redist" || game.get("is_dlc").and_then(Value::as_bool) == Some(true) {
            continue;
        }
        if let Some(title) = titles.get(app) {
            found.push(Found { name: title.clone(), app: app.into(), runner: "gog", label: "gog" });
        }
    }

    // Amazon: installed ids, titles in nile's library.
    let titles: HashMap<String, String> = read(&root.join("nile_config/nile/library.json"))
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(|entry| {
            let product = entry.get("product")?;
            Some((text(product, "id")?.to_string(), text(product, "title")?.to_string()))
        })
        .collect();
    for game in read(&root.join("nile_config/nile/installed.json")).as_array().into_iter().flatten() {
        if let Some(app) = text(game, "id")
            && let Some(title) = titles.get(app)
        {
            found.push(Found { name: title.clone(), app: app.into(), runner: "nile", label: "amazon" });
        }
    }

    // Added by hand; entries with a browser URL are web pages, not programs.
    for game in read(&root.join("sideload_apps/library.json")).get("games").and_then(Value::as_array).into_iter().flatten() {
        let installed = game.get("is_installed").and_then(Value::as_bool).unwrap_or(true);
        if !installed || game.get("browserUrl").is_some_and(|url| !url.is_null()) {
            continue;
        }
        if let (Some(app), Some(title)) = (text(game, "app_name"), text(game, "title")) {
            found.push(Found { name: title.into(), app: app.into(), runner: "sideload", label: "heroic" });
        }
    }
    found
}

#[cfg(test)]
mod tests {
    use super::*;

    fn write(root: &Path, file: &str, text: &str) {
        let path = root.join(file);
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(path, text).unwrap();
    }

    #[test]
    fn every_store_is_read_and_extras_are_skipped() {
        let root = std::env::temp_dir().join(format!("hanami-heroic-{}", std::process::id()));
        write(&root, "legendaryConfig/legendary/installed.json", r#"{
            "Fortnite": {"app_name": "Fortnite", "title": "Fortnite", "is_dlc": false},
            "Pack": {"app_name": "Pack", "title": "Some DLC", "is_dlc": true}}"#);
        write(&root, "store_cache/gog_library.json", r#"{"games": [
            {"app_name": "1207658924", "title": "Unreal Gold"},
            {"app_name": "gog-redist", "title": "Galaxy Common Redistributables"}],
            "__timestamp.games": 1}"#);
        write(&root, "gog_store/installed.json", r#"{"installed": [
            {"appName": "1207658924", "platform": "windows"}, {"appName": "gog-redist"}]}"#);
        write(&root, "nile_config/nile/library.json", r#"[{"product": {"id": "amzn1.x", "title": "Amazon Game"}}]"#);
        write(&root, "nile_config/nile/installed.json", r#"[{"id": "amzn1.x", "path": "/g"}, {"id": "amzn1.unknown"}]"#);
        write(&root, "sideload_apps/library.json", r#"{"games": [
            {"app_name": "abc", "title": "My Emulator", "is_installed": true},
            {"app_name": "web", "title": "Web Game", "browserUrl": "https://x"},
            {"app_name": "gone", "title": "Removed", "is_installed": false}]}"#);

        let mut found = installed(&root);
        found.sort_by(|a, b| a.name.cmp(&b.name));
        let names: Vec<_> = found.iter().map(|f| (f.name.as_str(), f.runner, f.label)).collect();
        assert_eq!(
            names,
            [
                ("Amazon Game", "nile", "amazon"),
                ("Fortnite", "legendary", "epic"),
                ("My Emulator", "sideload", "heroic"),
                ("Unreal Gold", "gog", "gog"),
            ]
        );
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn launch_urls_native_and_flatpak() {
        let found = || Found { name: "X".into(), app: "Fort nite".into(), runner: "legendary", label: "epic" };
        assert_eq!(found().into_game(false).launch, Launch::Open("heroic://launch?appName=Fort%20nite&runner=legendary".into()));
        let Launch::Command { program, args, .. } = found().into_game(true).launch else { panic!() };
        assert_eq!(program, PathBuf::from("flatpak"));
        assert_eq!(args[1], FLATPAK_ID);
    }

    #[test]
    fn missing_folder_finds_nothing() {
        assert!(installed(Path::new("/nonexistent/heroic")).is_empty());
    }
}
