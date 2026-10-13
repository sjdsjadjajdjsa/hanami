//! What Hanami remembers by itself, apart from the settings: when each game
//! was last played and which found games the user chose to keep.

use std::collections::{BTreeMap, BTreeSet};
use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};

use crate::games::key;

#[derive(Debug, Default, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct State {
    /// Game name key to the time it was last started, in seconds.
    pub played: BTreeMap<String, u64>,
    /// Name keys of found games the user said yes to.
    pub kept: BTreeSet<String>,
}

pub fn path() -> Option<PathBuf> {
    dirs::data_local_dir().map(|dir| dir.join("hanami").join("state.toml"))
}

impl State {
    /// A missing or damaged file starts over; nothing in it is precious.
    pub fn load() -> Self {
        path()
            .and_then(|path| std::fs::read_to_string(path).ok())
            .and_then(|text| toml::from_str(&text).ok())
            .unwrap_or_default()
    }

    pub fn save(&self) -> Result<(), String> {
        let path = path().ok_or("no place for Hanami's data")?;
        if let Some(dir) = path.parent() {
            std::fs::create_dir_all(dir).map_err(|e| e.to_string())?;
        }
        let text = toml::to_string(self).map_err(|e| e.to_string())?;
        crate::config::write_atomic(&path, &text)
    }

    pub fn played_now(&mut self, name: &str) {
        let now = SystemTime::now().duration_since(UNIX_EPOCH).map_or(0, |time| time.as_secs());
        self.played.insert(key(name), now);
    }

    /// Carries what is remembered about a game over to its new name.
    pub fn renamed(&mut self, from: &str, to: &str) {
        let (from, to) = (key(from), key(to));
        if let Some(time) = self.played.remove(&from) {
            self.played.insert(to.clone(), time);
        }
        if self.kept.remove(&from) {
            self.kept.insert(to);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn round_trips_and_follows_renames() {
        let mut state = State::default();
        state.played_now("Hollow Knight");
        state.kept.insert(key("Ship of Harkinian"));
        state.renamed("Hollow Knight", "HK");
        state.renamed("Ship of Harkinian", "SoH");
        assert!(state.played.contains_key("hk") && !state.played.contains_key("hollowknight"));
        assert!(state.kept.contains("soh"));
        let text = toml::to_string(&state).unwrap();
        assert_eq!(toml::from_str::<State>(&text).unwrap(), state);
        assert_eq!(toml::from_str::<State>("").unwrap(), State::default());
    }
}
