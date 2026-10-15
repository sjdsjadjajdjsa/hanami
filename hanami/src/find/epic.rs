//! Games installed through the Epic Games Launcher on Windows, read from
//! its manifest files; Epic launches them itself.

use std::path::Path;

use serde_json::Value;

use crate::games::{Game, Launch};

#[cfg(windows)]
pub fn find() -> Vec<Game> {
    let base =
        std::env::var_os("PROGRAMDATA").map(std::path::PathBuf::from).unwrap_or_else(|| r"C:\ProgramData".into());
    let Ok(entries) = std::fs::read_dir(base.join(r"Epic\EpicGamesLauncher\Data\Manifests")) else { return Vec::new() };
    entries
        .flatten()
        .map(|entry| entry.path())
        .filter(|path| path.extension().is_some_and(|ext| ext == "item"))
        .filter_map(|path| std::fs::read_to_string(path).ok())
        .filter_map(|text| from_manifest(&text, Path::is_file))
        .collect()
}

/// One manifest, if it is a complete, launchable game (not DLC or an engine).
/// Its icon is the game's own exe, when `exists` says the manifest's path is real.
fn from_manifest(text: &str, exists: impl Fn(&Path) -> bool) -> Option<Game> {
    let manifest: Value = serde_json::from_str(text).ok()?;
    let field = |key: &str| manifest.get(key).and_then(Value::as_str).filter(|s| !s.is_empty());
    if manifest.get("bIsIncompleteInstall").and_then(Value::as_bool) == Some(true) {
        return None;
    }
    let categories: Vec<&str> = manifest
        .get("AppCategories")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(Value::as_str)
        .collect();
    let addon = categories.contains(&"addons") && !categories.contains(&"addons/launchable");
    let engine = categories.iter().any(|c| c.starts_with("plugins"));
    if addon || engine {
        return None;
    }
    let (name, app) = (field("DisplayName")?, field("AppName")?);
    let url = match (field("CatalogNamespace"), field("CatalogItemId")) {
        (Some(namespace), Some(item)) => format!(
            "com.epicgames.launcher://apps/{}%3A{}%3A{}?action=launch&silent=true",
            super::encode(namespace),
            super::encode(item),
            super::encode(app)
        ),
        _ => format!("com.epicgames.launcher://apps/{}?action=launch&silent=true", super::encode(app)),
    };
    let icon = match (field("InstallLocation"), field("LaunchExecutable")) {
        (Some(folder), Some(exe)) => Some(Path::new(folder).join(exe)).filter(|path| exists(path)),
        _ => None,
    };
    Some(Game { group: None, name: name.into(), label: "epic".into(), launch: Launch::Open(url), icon })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn games_are_read_and_dlc_engines_and_partial_installs_skipped() {
        let game = r#"{"DisplayName": "Hades", "AppName": "Min", "CatalogNamespace": "ns", "CatalogItemId": "item",
                       "AppCategories": ["public", "games", "applications"],
                       "InstallLocation": "C:\\Games\\Hades", "LaunchExecutable": "x64\\Hades.exe"}"#;
        let found = from_manifest(game, |_| true).unwrap();
        assert_eq!(found.name, "Hades");
        assert_eq!(
            found.launch,
            Launch::Open("com.epicgames.launcher://apps/ns%3Aitem%3AMin?action=launch&silent=true".into())
        );
        assert_eq!(found.icon, Some(Path::new(r"C:\Games\Hades").join(r"x64\Hades.exe")));
        assert_eq!(from_manifest(game, |_| false).unwrap().icon, None);

        let dlc = r#"{"DisplayName": "Pack", "AppName": "P", "AppCategories": ["addons"]}"#;
        let launchable_dlc =
            r#"{"DisplayName": "Mode", "AppName": "M", "AppCategories": ["addons", "addons/launchable"]}"#;
        let engine = r#"{"DisplayName": "UE", "AppName": "UE_5", "AppCategories": ["plugins/engine"]}"#;
        let partial = r#"{"DisplayName": "Big", "AppName": "B", "bIsIncompleteInstall": true}"#;
        assert!(from_manifest(dlc, |_| true).is_none());
        assert!(from_manifest(launchable_dlc, |_| true).is_some());
        assert!(from_manifest(engine, |_| true).is_none());
        assert!(from_manifest(partial, |_| true).is_none());
        assert!(from_manifest("not json", |_| true).is_none());
    }
}
