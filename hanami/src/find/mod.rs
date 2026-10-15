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
mod ports;
mod prism;
mod steam;

use std::cell::RefCell;

use serde::Deserialize;

use crate::config::Config;
use crate::games::Game;

thread_local! {
    static PROBLEMS: RefCell<Vec<String>> = const { RefCell::new(Vec::new()) };
}

/// A place that is there but couldn't be read: said once in the panel and in
/// `--list`, so an empty list isn't mistaken for "no games". A place that
/// simply isn't installed says nothing.
pub(crate) fn report(place: &str, what: impl std::fmt::Display) {
    PROBLEMS.with_borrow_mut(|problems| problems.push(format!("{place}: {what}")));
}

/// The problems reported since the last call.
pub fn problems() -> Vec<String> {
    PROBLEMS.with_borrow_mut(std::mem::take)
}

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
    /// Minecraft instances from Prism Launcher, PolyMC and MultiMC.
    Prism,
}

impl Source {
    pub const ALL: [Source; 8] = [
        Source::Steam,
        Source::Heroic,
        Source::Lutris,
        Source::Apps,
        Source::Epic,
        Source::Gog,
        Source::Ports,
        Source::Prism,
    ];
}

/// Scans for ports right away instead of in the background, for `--list`.
pub use ports::{on_change as on_ports_change, scan_now as scan_ports};
#[cfg(test)]
pub use steam::launch as steam_launch;

/// The config is for `ports` (`folders`, `projects`, `online`) and `prism` (`folders`).
pub fn games(source: Source, config: &Config) -> Vec<Game> {
    match source {
        Source::Steam => steam::find(),
        Source::Heroic => heroic::find(),
        Source::Prism => prism::find(config),
        Source::Ports => ports::find(config),
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
