//! Installed Steam games, without Steam's own tools.

use std::path::{Path, PathBuf};

use crate::games::{Game, Launch};

pub fn find() -> Vec<Game> {
    let Ok(steam) = steamlocate::SteamDir::locate() else { return Vec::new() };
    let Ok(libraries) = steam.libraries() else { return Vec::new() };
    let icons = Icons::new(steam.path());
    libraries
        .flatten()
        .flat_map(|library| library.apps().flatten().collect::<Vec<_>>())
        .filter(|app| app.state_flags.is_none_or(|flags| flags.0 & FULLY_INSTALLED != 0))
        .map(|app| (app.app_id, app.name.unwrap_or(app.install_dir)))
        .filter(|(_, name)| !is_tool(name))
        .map(|(id, name)| Game { name, label: "steam".into(), launch: launch(id), icon: icons.find(id) })
        .collect()
}

/// Where Steam keeps each game's small square icon. The library cache has a
/// 32 px jpeg per game, named after the icon's hash; when the user made a
/// desktop shortcut there is also a full-size `.ico` with the same hash and,
/// on Linux, pngs in the hicolor theme.
struct Icons {
    cache: PathBuf,
    icos: PathBuf,
    hicolor: Option<PathBuf>,
}

impl Icons {
    fn new(steam: &Path) -> Self {
        let hicolor = if cfg!(target_os = "linux") { dirs::data_dir().map(|d| d.join("icons/hicolor")) } else { None };
        Self::at(steam, hicolor.filter(|dir| dir.is_dir()))
    }

    fn at(steam: &Path, hicolor: Option<PathBuf>) -> Self {
        Self { cache: steam.join("appcache/librarycache"), icos: steam.join("steam/games"), hicolor }
    }

    fn find(&self, id: u32) -> Option<PathBuf> {
        if let Some(hicolor) = &self.hicolor {
            let png = ["128x128", "256x256", "64x64", "48x48", "32x32"]
                .iter()
                .map(|size| hicolor.join(size).join(format!("apps/steam_icon_{id}.png")))
                .find(|path| path.is_file());
            if png.is_some() {
                return png;
            }
        }
        let small =
            self.hashed_jpeg(id).or_else(|| Some(self.cache.join(format!("{id}_icon.jpg"))).filter(|p| p.is_file()))?;
        let ico = small.file_stem().map(|hash| self.icos.join(hash).with_extension("ico")).filter(|p| p.is_file());
        ico.or(Some(small))
    }

    /// `librarycache/<id>/<40 hex digits>.jpg`; the wide art sits in
    /// subfolders with the same kind of name.
    fn hashed_jpeg(&self, id: u32) -> Option<PathBuf> {
        std::fs::read_dir(self.cache.join(id.to_string())).ok()?.flatten().map(|entry| entry.path()).find(|path| {
            path.extension().is_some_and(|ext| ext == "jpg")
                && path.file_stem().and_then(|stem| stem.to_str()).is_some_and(is_hash)
        })
    }
}

fn is_hash(stem: &str) -> bool {
    stem.len() == 40 && stem.bytes().all(|b| b.is_ascii_hexdigit())
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
    use super::*;

    fn touch(path: PathBuf) -> PathBuf {
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(&path, "").unwrap();
        path
    }

    #[test]
    fn icons_prefer_big_pngs_then_icos_then_the_small_jpeg() {
        let root = std::env::temp_dir().join(format!("hanami-steam-{}", std::process::id()));
        let (steam, hicolor) = (root.join("steam"), root.join("hicolor"));
        let hash = "03ac7d28e21f420f5e0ae72d783bf6d639041542";
        let jpeg = touch(steam.join(format!("appcache/librarycache/1/{hash}.jpg")));
        touch(steam.join(format!("appcache/librarycache/1/{hash}/library_hero.jpg")));
        touch(steam.join("appcache/librarycache/1/header.jpg"));
        let icons = Icons::at(&steam, Some(hicolor.clone()));
        assert_eq!(icons.find(1), Some(jpeg));
        let ico = touch(steam.join(format!("steam/games/{hash}.ico")));
        assert_eq!(icons.find(1), Some(ico));
        touch(hicolor.join("32x32/apps/steam_icon_1.png"));
        let big = touch(hicolor.join("128x128/apps/steam_icon_1.png"));
        assert_eq!(icons.find(1), Some(big));

        let old = touch(steam.join("appcache/librarycache/2_icon.jpg"));
        assert_eq!(icons.find(2), Some(old));
        assert_eq!(icons.find(3), None);
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn tools_are_recognised_and_games_are_not() {
        for tool in [
            "Proton 10.0",
            "Proton Experimental",
            "Steam Linux Runtime 3.0 (sniper)",
            "Steamworks Common Redistributables",
        ] {
            assert!(is_tool(tool), "{tool}");
        }
        for game in ["Counter-Strike 2", "Portal 2", "SteamWorld Dig"] {
            assert!(!is_tool(game), "{game}");
        }
    }
}
