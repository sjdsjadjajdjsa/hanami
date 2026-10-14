//! Games installed through Heroic: Epic (legendary), GOG, Amazon (nile) and
//! programs added by hand ("sideloaded"). Heroic launches them itself.

use std::collections::HashMap;
use std::path::{Path, PathBuf};

use serde_json::Value;
use sha2::{Digest, Sha256};

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
    let mut roots: Vec<(PathBuf, bool)> =
        dirs::config_dir().map(|dir| (dir.join("heroic"), false)).into_iter().collect();
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
    icon: Option<PathBuf>,
}

impl Found {
    fn into_game(self, flatpak: bool) -> Game {
        let url = format!("heroic://launch?appName={}&runner={}", super::encode(&self.app), self.runner);
        let launch = if flatpak {
            Launch::Command {
                program: "flatpak".into(),
                args: vec!["run".into(), FLATPAK_ID.into(), url],
                dir: None,
                env: Vec::new(),
            }
        } else {
            Launch::Open(url)
        };
        Game { name: self.name, label: self.label.into(), launch, icon: self.icon }
    }
}

/// Heroic's downloaded art: `images-cache/<sha256 of the picture's URL>`
/// (src/backend/images_cache.ts). The library asks for Epic covers with a
/// resize query and the game page for a bigger one, so all forms are tried.
fn cached_art(root: &Path, urls: &[&str]) -> Option<PathBuf> {
    let cache = root.join("images-cache");
    urls.iter()
        .flat_map(|url| [url.to_string(), format!("{url}?h=400&resize=1&w=300"), format!("{url}?h=800&resize=1&w=600")])
        .map(|url| cache.join(hex(&Sha256::digest(url.as_bytes()))))
        .find(|path| path.is_file())
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

/// A game's square picture, in order: Heroic's cached art, GOG's own icon
/// file in the game folder, or (on Windows) the game's exe.
fn icon(root: &Path, urls: &[&str], folder: Option<&Path>, app: &str, exe: Option<&str>) -> Option<PathBuf> {
    cached_art(root, urls)
        .or_else(|| folder.map(|dir| dir.join(format!("goggame-{app}.ico"))).filter(|path| path.is_file()))
        .or_else(|| {
            let exe = folder.zip(exe).filter(|_| cfg!(windows)).map(|(dir, exe)| dir.join(exe))?;
            exe.is_file().then_some(exe)
        })
}

/// The picture URLs Epic knows for a game, from legendary's metadata.
fn epic_art(root: &Path, app: &str) -> Vec<String> {
    let metadata = read(&root.join(format!("legendaryConfig/legendary/metadata/{app}.json")));
    let images = metadata.get("metadata").and_then(|m| m.get("keyImages")).and_then(Value::as_array);
    let mut urls: Vec<(usize, String)> = images
        .into_iter()
        .flatten()
        .filter_map(|image| {
            let rank = ["DieselGameBoxTall", "DieselGameBox", "DieselGameBoxLogo"]
                .iter()
                .position(|t| Some(*t) == text(image, "type"))?;
            Some((rank, text(image, "url")?.to_string()))
        })
        .collect();
    urls.sort();
    urls.into_iter().map(|(_, url)| url).collect()
}

fn read(path: &Path) -> Value {
    std::fs::read_to_string(path).ok().and_then(|text| serde_json::from_str(&text).ok()).unwrap_or(Value::Null)
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
                let urls = epic_art(root, app);
                let urls: Vec<&str> = urls.iter().map(String::as_str).collect();
                let folder = text(game, "install_path").map(Path::new);
                let icon = icon(root, &urls, folder, app, text(game, "executable"));
                found.push(Found { name: title.into(), app: app.into(), runner: "legendary", label: "epic", icon });
            }
        }
    }

    // GOG: installed ids here, titles and art in the library cache.
    let titles: HashMap<String, (String, Vec<String>)> = read(&root.join("store_cache/gog_library.json"))
        .get("games")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|game| {
            let art = ["art_square", "art_cover"].iter().filter_map(|key| text(game, key)).map(String::from).collect();
            Some((text(game, "app_name")?.to_string(), (text(game, "title")?.to_string(), art)))
        })
        .collect();
    for game in
        read(&root.join("gog_store/installed.json")).get("installed").and_then(Value::as_array).into_iter().flatten()
    {
        let Some(app) = text(game, "appName") else { continue };
        if app == "gog-redist" || game.get("is_dlc").and_then(Value::as_bool) == Some(true) {
            continue;
        }
        if let Some((title, art)) = titles.get(app) {
            let urls: Vec<&str> = art.iter().map(String::as_str).collect();
            let folder = text(game, "install_path").map(Path::new);
            let icon = icon(root, &urls, folder, app, None);
            found.push(Found { name: title.clone(), app: app.into(), runner: "gog", label: "gog", icon });
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
            found.push(Found { name: title.clone(), app: app.into(), runner: "nile", label: "amazon", icon: None });
        }
    }

    // Added by hand; entries with a browser URL are web pages, not programs.
    // Their picture is a file the user picked, or a downloaded one.
    for game in
        read(&root.join("sideload_apps/library.json")).get("games").and_then(Value::as_array).into_iter().flatten()
    {
        let installed = game.get("is_installed").and_then(Value::as_bool).unwrap_or(true);
        if !installed || game.get("browserUrl").is_some_and(|url| !url.is_null()) {
            continue;
        }
        if let (Some(app), Some(title)) = (text(game, "app_name"), text(game, "title")) {
            let art = ["art_square", "art_cover"].iter().filter_map(|key| text(game, key)).collect::<Vec<_>>();
            let icon = art
                .iter()
                .map(Path::new)
                .find(|path| path.is_absolute() && path.is_file())
                .map(Path::to_path_buf)
                .or_else(|| cached_art(root, &art));
            found.push(Found { name: title.into(), app: app.into(), runner: "sideload", label: "heroic", icon });
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
        let unreal = root.join("games/unreal");
        write(
            &root,
            "legendaryConfig/legendary/installed.json",
            r#"{
            "Fortnite": {"app_name": "Fortnite", "title": "Fortnite", "is_dlc": false},
            "Pack": {"app_name": "Pack", "title": "Some DLC", "is_dlc": true}}"#,
        );
        write(
            &root,
            "legendaryConfig/legendary/metadata/Fortnite.json",
            r#"{"metadata": {"keyImages": [
            {"type": "DieselGameBox", "url": "https://cdn/wide.jpg"},
            {"type": "DieselGameBoxTall", "url": "https://cdn/tall.jpg"}]}}"#,
        );
        write(
            &root,
            &format!("images-cache/{}", hex(&Sha256::digest(b"https://cdn/tall.jpg?h=400&resize=1&w=300"))),
            "",
        );
        write(
            &root,
            "store_cache/gog_library.json",
            r#"{"games": [
            {"app_name": "1207658924", "title": "Unreal Gold", "art_square": "https://gog/x.jpg"},
            {"app_name": "gog-redist", "title": "Galaxy Common Redistributables"}],
            "__timestamp.games": 1}"#,
        );
        write(
            &root,
            "gog_store/installed.json",
            &format!(
                r#"{{"installed": [
            {{"appName": "1207658924", "platform": "windows", "install_path": {:?}}}, {{"appName": "gog-redist"}}]}}"#,
                unreal
            ),
        );
        write(&unreal, "goggame-1207658924.ico", "");
        write(&root, "nile_config/nile/library.json", r#"[{"product": {"id": "amzn1.x", "title": "Amazon Game"}}]"#);
        write(
            &root,
            "nile_config/nile/installed.json",
            r#"[{"id": "amzn1.x", "path": "/g"}, {"id": "amzn1.unknown"}]"#,
        );
        write(
            &root,
            "sideload_apps/library.json",
            &format!(
                r#"{{"games": [
            {{"app_name": "abc", "title": "My Emulator", "is_installed": true, "art_cover": {:?}}},
            {{"app_name": "web", "title": "Web Game", "browserUrl": "https://x"}},
            {{"app_name": "gone", "title": "Removed", "is_installed": false}}]}}"#,
                unreal.join("cover.png")
            ),
        );
        write(&unreal, "cover.png", "");

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
        let icons: Vec<_> = found.iter().map(|f| f.icon.clone()).collect();
        assert_eq!(icons[0], None);
        assert!(icons[1].as_ref().unwrap().starts_with(root.join("images-cache")));
        assert_eq!(icons[2], Some(unreal.join("cover.png")));
        assert_eq!(icons[3], Some(unreal.join("goggame-1207658924.ico")));
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn launch_urls_native_and_flatpak() {
        let found =
            || Found { name: "X".into(), app: "Fort nite".into(), runner: "legendary", label: "epic", icon: None };
        assert_eq!(
            found().into_game(false).launch,
            Launch::Open("heroic://launch?appName=Fort%20nite&runner=legendary".into())
        );
        let Launch::Command { program, args, .. } = found().into_game(true).launch else { panic!() };
        assert_eq!(program, PathBuf::from("flatpak"));
        assert_eq!(args[1], FLATPAK_ID);
    }

    #[test]
    fn missing_folder_finds_nothing() {
        assert!(installed(Path::new("/nonexistent/heroic")).is_empty());
    }
}
