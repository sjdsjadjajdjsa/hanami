//! Games installed through the Epic Games Launcher on Windows, read from
//! its manifest files; Epic launches them itself.

use std::collections::HashSet;
use std::path::Path;

use serde_json::Value;

use crate::games::{Game, Launch};

#[cfg(windows)]
pub fn find() -> Vec<Game> {
    use std::path::PathBuf;

    let program_data = std::env::var_os("PROGRAMDATA").map(PathBuf::from).unwrap_or_else(|| r"C:\ProgramData".into());
    // The launcher says where it keeps its data; older installs don't.
    let data = registry_data_path().unwrap_or_else(|| program_data.join(r"Epic\EpicGamesLauncher\Data"));
    let entries = match std::fs::read_dir(data.join("Manifests")) {
        Ok(entries) => entries,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Vec::new(),
        Err(error) => {
            super::report("Epic", format!("couldn't read its game list: {error}"));
            return Vec::new();
        }
    };
    // Manifests of uninstalled games can stay behind; this list is what's really there.
    let installed = std::fs::read_to_string(program_data.join(r"Epic\UnrealEngineLauncher\LauncherInstalled.dat"))
        .ok()
        .and_then(|text| installed(&text));
    entries
        .flatten()
        .map(|entry| entry.path())
        .filter(|path| path.extension().is_some_and(|ext| ext == "item"))
        .filter_map(|path| std::fs::read_to_string(path).ok())
        .filter_map(|text| from_manifest(&text, installed.as_ref(), Path::is_file))
        .collect()
}

#[cfg(windows)]
fn registry_data_path() -> Option<std::path::PathBuf> {
    use winreg::RegKey;
    use winreg::enums::HKEY_LOCAL_MACHINE;

    let machine = RegKey::predef(HKEY_LOCAL_MACHINE);
    [r"SOFTWARE\WOW6432Node\Epic Games\EpicGamesLauncher", r"SOFTWARE\Epic Games\EpicGamesLauncher"]
        .into_iter()
        .filter_map(|path| machine.open_subkey(path).ok())
        .filter_map(|key| key.get_value::<String, _>("AppDataPath").ok())
        .map(std::path::PathBuf::from)
        .find(|path| path.is_dir())
}

/// The apps LauncherInstalled.dat lists, or `None` when it can't be read
/// (then every manifest counts).
fn installed(text: &str) -> Option<HashSet<String>> {
    let list: Value = serde_json::from_str(without_bom(text)).ok()?;
    let apps = list.get("InstallationList")?.as_array()?;
    Some(apps.iter().filter_map(|app| app.get("AppName")?.as_str()).map(String::from).collect())
}

/// Epic writes some files with a byte order mark, which JSON parsers refuse.
fn without_bom(text: &str) -> &str {
    text.strip_prefix('\u{feff}').unwrap_or(text)
}

/// One manifest, if it is a complete, launchable game (not DLC or an engine).
/// Its icon is the game's own exe, when `exists` says the manifest's path is real.
fn from_manifest(text: &str, installed: Option<&HashSet<String>>, exists: impl Fn(&Path) -> bool) -> Option<Game> {
    let manifest: Value = serde_json::from_str(without_bom(text)).ok()?;
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
    if installed.is_some_and(|installed| !installed.contains(app)) {
        return None;
    }
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
        let found = from_manifest(game, None, |_| true).unwrap();
        assert_eq!(found.name, "Hades");
        assert_eq!(
            found.launch,
            Launch::Open("com.epicgames.launcher://apps/ns%3Aitem%3AMin?action=launch&silent=true".into())
        );
        assert_eq!(found.icon, Some(Path::new(r"C:\Games\Hades").join(r"x64\Hades.exe")));
        assert_eq!(from_manifest(game, None, |_| false).unwrap().icon, None);

        let dlc = r#"{"DisplayName": "Pack", "AppName": "P", "AppCategories": ["addons"]}"#;
        let launchable_dlc =
            r#"{"DisplayName": "Mode", "AppName": "M", "AppCategories": ["addons", "addons/launchable"]}"#;
        let engine = r#"{"DisplayName": "UE", "AppName": "UE_5", "AppCategories": ["plugins/engine"]}"#;
        let partial = r#"{"DisplayName": "Big", "AppName": "B", "bIsIncompleteInstall": true}"#;
        assert!(from_manifest(dlc, None, |_| true).is_none());
        assert!(from_manifest(launchable_dlc, None, |_| true).is_some());
        assert!(from_manifest(engine, None, |_| true).is_none());
        assert!(from_manifest(partial, None, |_| true).is_none());
        assert!(from_manifest("not json", None, |_| true).is_none());
    }

    #[test]
    fn byte_order_marks_are_skipped() {
        let game = "\u{feff}{\"DisplayName\": \"Hades\", \"AppName\": \"Min\"}";
        assert_eq!(from_manifest(game, None, |_| true).unwrap().name, "Hades");
    }

    #[test]
    fn manifests_left_behind_by_uninstalls_are_skipped() {
        let dat =
            "\u{feff}{\"InstallationList\": [{\"InstallLocation\": \"C:\\\\Games\\\\Hades\", \"AppName\": \"Min\"}]}";
        let installed = installed(dat).unwrap();
        let hades = r#"{"DisplayName": "Hades", "AppName": "Min"}"#;
        let gone = r#"{"DisplayName": "Gone", "AppName": "Old"}"#;
        assert!(from_manifest(hades, Some(&installed), |_| true).is_some());
        assert!(from_manifest(gone, Some(&installed), |_| true).is_none());
        // An unreadable list leaves the manifests alone.
        assert_eq!(super::installed("not json"), None);
        assert_eq!(super::installed("{}"), None);
    }
}
