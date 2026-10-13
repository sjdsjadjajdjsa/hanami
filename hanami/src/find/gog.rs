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
            // Older games run inside DOSBox or ScummVM, told what to load here.
            let args = value("launchParam").map(|line| split(&line)).unwrap_or_default();
            if games.iter().any(|game: &Game| game.name == name) {
                continue;
            }
            games.push(Game {
                name,
                label: "gog".into(),
                launch: Launch::Command { program: PathBuf::from(exe), args, dir: value("workingDir").map(PathBuf::from) },
                icon: None,
            });
        }
    }
    games
}

/// Splits a command line like `-conf "..\a b.conf" -noconsole` into arguments.
fn split(line: &str) -> Vec<String> {
    let mut args = Vec::new();
    let mut arg = String::new();
    let (mut quoted, mut started) = (false, false);
    for c in line.chars() {
        match c {
            '"' => {
                quoted = !quoted;
                started = true;
            }
            c if c.is_whitespace() && !quoted => {
                if started {
                    args.push(std::mem::take(&mut arg));
                    started = false;
                }
            }
            c => {
                arg.push(c);
                started = true;
            }
        }
    }
    if started {
        args.push(arg);
    }
    args
}

#[cfg(test)]
mod tests {
    use super::split;

    #[test]
    fn quoted_parts_stay_whole() {
        assert_eq!(
            split(r#"-conf "..\dosbox game.conf" -noconsole  -c "exit" """#),
            [r"-conf", r"..\dosbox game.conf", "-noconsole", "-c", "exit", ""]
        );
        assert!(split("  ").is_empty());
    }
}
