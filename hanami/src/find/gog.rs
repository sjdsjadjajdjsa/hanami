//! Games installed from GOG (Galaxy or the offline installers) on Windows,
//! read from the registry entries their installers write.

use std::path::PathBuf;

use winreg::RegKey;
use winreg::enums::HKEY_LOCAL_MACHINE;

use crate::games::{Game, Launch};

pub fn find() -> Vec<Game> {
    let machine = RegKey::predef(HKEY_LOCAL_MACHINE);
    let mut games = Vec::new();
    for path in [r"SOFTWARE\WOW6432Node\GOG.com\Games", r"SOFTWARE\GOG.com\Games"] {
        let Ok(list) = machine.open_subkey(path) else { continue };
        for id in list.enum_keys().flatten() {
            let Ok(key) = list.open_subkey(&id) else { continue };
            let value = |name: &str| key.get_value::<String, _>(name).ok().filter(|v| !v.is_empty());
            // DLC entries point at the game they belong to.
            if value("dependsOn").is_some() {
                continue;
            }
            let (Some(name), Some(exe)) = (value("gameName"), value("exe")) else { continue };
            if games.iter().any(|game: &Game| game.name == name) {
                continue;
            }
            games.push(Game {
                name,
                label: "gog".into(),
                launch: Launch::Command { program: PathBuf::from(exe), args: Vec::new(), dir: value("workingDir").map(PathBuf::from) },
            });
        }
    }
    games
}
