//! Where Hanami looks for installed games. Each place returns ready-to-launch
//! games; places that don't exist on this computer just return nothing.

#[cfg(target_os = "linux")]
mod apps;
#[cfg(any(windows, test))]
mod epic;
#[cfg(windows)]
mod gog;
mod heroic;
#[cfg(target_os = "linux")]
mod icon_theme;
#[cfg(target_os = "linux")]
mod lutris;
mod steam;

use serde::Deserialize;

use crate::games::Game;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Source {
    Steam,
    Heroic,
    Lutris,
    Apps,
    Epic,
    Gog,
    /// Game ports and rewrites, games with a hanami-game.toml, and games
    /// built in the `projects` folders.
    Ports,
}

impl Source {
    pub const ALL: [Source; 7] =
        [Source::Steam, Source::Heroic, Source::Lutris, Source::Apps, Source::Epic, Source::Gog, Source::Ports];
}

#[cfg(test)]
pub use steam::launch as steam_launch;

pub fn games(source: Source) -> Vec<Game> {
    match source {
        Source::Steam => steam::find(),
        Source::Heroic => heroic::find(),
        #[cfg(target_os = "linux")]
        Source::Lutris => lutris::find(),
        #[cfg(target_os = "linux")]
        Source::Apps => apps::find(),
        #[cfg(windows)]
        Source::Epic => epic::find(),
        #[cfg(windows)]
        Source::Gog => gog::find(),
        #[allow(unreachable_patterns)]
        _ => Vec::new(),
    }
}

/// `%`-encodes everything but letters, digits and `-._~`, for building URLs.
fn encode(text: &str) -> String {
    text.bytes()
        .map(|b| match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'.' | b'_' | b'~' => (b as char).to_string(),
            _ => format!("%{b:02X}"),
        })
        .collect()
}

#[cfg(test)]
mod tests {
    #[test]
    fn encode_keeps_safe_characters_only() {
        assert_eq!(super::encode("Fortnite:a b/c"), "Fortnite%3Aa%20b%2Fc");
        assert_eq!(super::encode("abc-1.2_~"), "abc-1.2_~");
    }
}
