//! Installed Steam games, without Steam's own tools.

use crate::games::{Game, Launch};

pub fn find() -> Vec<Game> {
    let Ok(steam) = steamlocate::SteamDir::locate() else { return Vec::new() };
    let Ok(libraries) = steam.libraries() else { return Vec::new() };
    libraries
        .flatten()
        .flat_map(|library| library.apps().flatten().collect::<Vec<_>>())
        .filter(|app| app.state_flags.is_none_or(|flags| flags.0 & FULLY_INSTALLED != 0))
        .map(|app| (app.app_id, app.name.unwrap_or(app.install_dir)))
        .filter(|(_, name)| !is_tool(name))
        .map(|(id, name)| Game { name, label: "steam".into(), launch: launch(id) })
        .collect()
}

/// Steam's "fully installed" state bit; games mid-download don't have it.
const FULLY_INSTALLED: u64 = 4;

pub fn launch(id: u32) -> Launch {
    Launch::Open(format!("steam://rungameid/{id}"))
}

/// Compatibility layers and runtimes Steam installs next to games.
fn is_tool(name: &str) -> bool {
    const TOOLS: [&str; 4] = ["Proton", "Steam Linux Runtime", "Steamworks Common Redistributables", "Steamworks SDK"];
    TOOLS.iter().any(|tool| name.starts_with(tool))
}

#[cfg(test)]
mod tests {
    use super::is_tool;

    #[test]
    fn tools_are_recognised_and_games_are_not() {
        for tool in ["Proton 10.0", "Proton Experimental", "Steam Linux Runtime 3.0 (sniper)", "Steamworks Common Redistributables"] {
            assert!(is_tool(tool), "{tool}");
        }
        for game in ["Counter-Strike 2", "Portal 2", "SteamWorld Dig"] {
            assert!(!is_tool(game), "{game}");
        }
    }
}
