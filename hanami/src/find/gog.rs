//! Games installed from GOG (Galaxy or the offline installers) on Windows,
//! read from the registry entries their installers write. With GOG Galaxy
//! installed they start through it, for its cloud saves and achievements.

use std::path::{Path, PathBuf};

use serde_json::Value;

use crate::games::{Game, Launch};

#[cfg(windows)]
pub fn find() -> Vec<Game> {
    use winreg::RegKey;
    use winreg::enums::HKEY_LOCAL_MACHINE;

    let machine = RegKey::predef(HKEY_LOCAL_MACHINE);
    let galaxy = galaxy(&machine);
    let mut games: Vec<Game> = Vec::new();
    for path in [r"SOFTWARE\WOW6432Node\GOG.com\Games", r"SOFTWARE\GOG.com\Games"] {
        let list = match machine.open_subkey(path) {
            Ok(list) => list,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => continue,
            Err(error) => {
                super::report("GOG", format!("couldn't read its game list: {error}"));
                continue;
            }
        };
        for id in list.enum_keys().flatten() {
            let Ok(key) = list.open_subkey(&id) else { continue };
            let value = |name: &str| key.get_value::<String, _>(name).ok();
            let read = |path: &Path| std::fs::read_to_string(path).ok();
            let Some(game) = from_entry(&id, value, read, Path::is_file, galaxy.as_deref()) else { continue };
            if !games.iter().any(|known| known.name == game.name) {
                games.push(game);
            }
        }
    }
    games
}

/// GalaxyClient.exe, when GOG Galaxy is installed.
#[cfg(windows)]
fn galaxy(machine: &winreg::RegKey) -> Option<PathBuf> {
    [r"SOFTWARE\WOW6432Node\GOG.com\GalaxyClient", r"SOFTWARE\GOG.com\GalaxyClient"]
        .into_iter()
        .filter_map(|path| {
            let client = machine.open_subkey(path).ok()?;
            let folder: String = client.open_subkey("paths").ok()?.get_value("client").ok()?;
            let exe = client.get_value::<String, _>("clientExecutable").unwrap_or_else(|_| "GalaxyClient.exe".into());
            Some(PathBuf::from(folder).join(exe))
        })
        .find(|exe| exe.is_file())
}

/// One game from its registry entry (`value` reads the entry's values), or
/// `None` for DLC and entries that can't be started. `read` reads files,
/// `exists` says whether a file is there.
fn from_entry(
    id: &str,
    value: impl Fn(&str) -> Option<String>,
    read: impl Fn(&Path) -> Option<String>,
    exists: impl Fn(&Path) -> bool,
    galaxy: Option<&Path>,
) -> Option<Game> {
    let value = |name: &str| value(name).filter(|v| !v.is_empty());
    // DLC entries point at the game they belong to.
    if value("dependsOn").is_some() {
        return None;
    }
    let name = value("gameName")?;
    let folder = value("path").map(PathBuf::from);
    let direct = match value("exe") {
        Some(exe) => Some(Launch::Command {
            program: PathBuf::from(exe),
            // Older games run inside DOSBox or ScummVM, told what to load here.
            args: value("launchParam").map(|line| split(&line)).unwrap_or_default(),
            dir: value("workingDir").map(PathBuf::from),
            env: Vec::new(),
        }),
        // Some installers leave `exe` empty; the game's own info file says how to start it.
        None => folder.as_ref().and_then(|folder| {
            let task = play_task(&read(&folder.join(format!("goggame-{id}.info")))?)?;
            Some(Launch::Command {
                program: folder.join(task.path),
                args: split(&task.arguments),
                dir: Some(folder.join(task.dir)),
                env: Vec::new(),
            })
        }),
    };
    // GOG puts the game's icon next to it; without it the game's exe is used
    // (not Galaxy's, when Galaxy starts it).
    let icon = [value("path"), value("workingDir")]
        .into_iter()
        .flatten()
        .map(|dir| PathBuf::from(dir).join(format!("goggame-{id}.ico")))
        .find(|path| exists(path))
        .or_else(|| match &direct {
            Some(Launch::Command { program, .. }) if exists(program) => Some(program.clone()),
            _ => None,
        });
    let launch = match (galaxy, &folder) {
        (Some(galaxy), Some(folder)) => Launch::Command {
            program: galaxy.into(),
            args: vec![
                "/command=runGame".into(),
                format!("/gameId={id}"),
                // A trailing backslash would escape the quote Windows puts around the path.
                format!("/path={}", folder.to_string_lossy().trim_end_matches('\\')),
            ],
            dir: None,
            env: Vec::new(),
        },
        _ => direct?,
    };
    Some(Game { group: None, name, label: "gog".into(), launch, icon })
}

/// How a game's `goggame-<id>.info` says to start it: its main play task.
struct PlayTask {
    path: String,
    arguments: String,
    dir: String,
}

fn play_task(info: &str) -> Option<PlayTask> {
    let info: Value = serde_json::from_str(info.strip_prefix('\u{feff}').unwrap_or(info)).ok()?;
    let tasks = info.get("playTasks")?.as_array()?;
    let task = tasks
        .iter()
        .find(|task| task.get("isPrimary").and_then(Value::as_bool) == Some(true))
        .or_else(|| tasks.first())?;
    let text = |key: &str| task.get(key).and_then(Value::as_str).unwrap_or_default().to_string();
    let path = text("path");
    if path.is_empty() {
        return None;
    }
    Some(PlayTask { path, arguments: text("arguments"), dir: text("workingDir") })
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
    use super::*;

    #[test]
    fn quoted_parts_stay_whole() {
        assert_eq!(
            split(r#"-conf "..\dosbox game.conf" -noconsole  -c "exit" """#),
            [r"-conf", r"..\dosbox game.conf", "-noconsole", "-c", "exit", ""]
        );
        assert!(split("  ").is_empty());
    }

    fn entry<'a>(values: &'a [(&str, &str)]) -> impl Fn(&str) -> Option<String> + 'a {
        |name| values.iter().find(|(key, _)| *key == name).map(|(_, value)| value.to_string())
    }

    fn program(game: &Game) -> (&Path, &[String]) {
        match &game.launch {
            Launch::Command { program, args, .. } => (program, args),
            Launch::Open(_) => panic!("gog games are commands"),
        }
    }

    #[test]
    fn games_start_directly_or_through_galaxy() {
        let values = [
            ("gameName", "Gwent"),
            ("exe", r"C:\GOG Games\Gwent\Gwent.exe"),
            ("path", r"C:\GOG Games\Gwent\"),
            ("workingDir", r"C:\GOG Games\Gwent"),
            ("launchParam", "-fast"),
        ];
        let direct = from_entry("1", entry(&values), |_| None, |_| true, None).unwrap();
        assert_eq!(direct.name, "Gwent");
        assert_eq!(program(&direct), (Path::new(r"C:\GOG Games\Gwent\Gwent.exe"), &["-fast".to_string()][..]));

        let galaxy = Path::new(r"C:\Galaxy\GalaxyClient.exe");
        let through = from_entry(
            "1",
            entry(&values),
            |_| None,
            |path| path.to_string_lossy().ends_with("Gwent.exe"),
            Some(galaxy),
        )
        .unwrap();
        assert_eq!(
            program(&through),
            (galaxy, &["/command=runGame".into(), "/gameId=1".into(), r"/path=C:\GOG Games\Gwent".into()][..])
        );
        // The row keeps the game's own icon, not Galaxy's.
        assert_eq!(through.icon, Some(PathBuf::from(r"C:\GOG Games\Gwent\Gwent.exe")));
    }

    #[test]
    fn dlc_and_unstartable_entries_are_skipped() {
        let dlc = [("gameName", "Pack"), ("exe", "a.exe"), ("dependsOn", "1")];
        assert!(from_entry("2", entry(&dlc), |_| None, |_| true, None).is_none());
        let nothing = [("gameName", "Nothing"), ("exe", "")];
        assert!(from_entry("3", entry(&nothing), |_| None, |_| true, None).is_none());
    }

    #[test]
    fn missing_exe_comes_from_the_info_file() {
        let values = [("gameName", "Old"), ("exe", ""), ("path", r"C:\GOG Games\Old")];
        let info = "\u{feff}{\"playTasks\": [
            {\"isPrimary\": false, \"path\": \"manual.pdf\"},
            {\"isPrimary\": true, \"path\": \"DOSBOX\\\\dosbox.exe\", \"arguments\": \"-conf \\\"a b.conf\\\"\", \"workingDir\": \"DOSBOX\"}
        ]}";
        let read = |path: &Path| path.ends_with("goggame-4.info").then(|| info.to_string());
        let game = from_entry("4", entry(&values), read, |_| false, None).unwrap();
        let folder = Path::new(r"C:\GOG Games\Old");
        assert_eq!(
            game.launch,
            Launch::Command {
                program: folder.join(r"DOSBOX\dosbox.exe"),
                args: vec!["-conf".into(), "a b.conf".into()],
                dir: Some(folder.join("DOSBOX")),
                env: Vec::new(),
            }
        );
        assert!(play_task(r#"{"playTasks": []}"#).is_none());
    }
}
