//! Game ports, recomps and rewrites found by themselves: the known ports in
//! ports.toml, in the usual folders and as Flatpaks; games that ship a
//! hanami-game.toml; and Rust games built in the `projects` folders.
//!
//! Looking through folders takes longer than the panel may wait, so the scan
//! runs on its own thread: `find` hands back the last result at once and
//! starts a new scan when that result is about a minute old.

mod list;
mod projects;

use std::collections::HashSet;
use std::path::{Path, PathBuf};
use std::sync::{Mutex, MutexGuard};
use std::time::{Duration, Instant};

use serde::Deserialize;
use walkdir::{DirEntry, WalkDir};

use crate::config::{Config, expand_home};
use crate::games::{Game, Launch};

const REFRESH: Duration = Duration::from_secs(60);
const SHIPPED: &str = "hanami-game.toml";
/// Folders never worth looking into: build output, source control, Wine and
/// Proton prefixes, Steam libraries (their games are found through Steam).
const SKIP: [&str; 13] = [
    "node_modules",
    ".git",
    "target",
    "vendor",
    "steamapps",
    "compatdata",
    "shadercache",
    "pfx",
    "drive_c",
    "dosdevices",
    ".wine",
    "__pycache__",
    "cache",
];

#[derive(Debug, Clone, PartialEq, Default)]
struct Settings {
    folders: Vec<PathBuf>,
    projects: Vec<PathBuf>,
    online: bool,
}

impl Settings {
    fn from(config: &Config) -> Self {
        let expand = |paths: &[String]| paths.iter().map(|path| expand_home(path)).collect();
        Settings { folders: expand(&config.folders), projects: expand(&config.projects), online: config.online }
    }
}

#[derive(Default)]
struct State {
    settings: Settings,
    games: Vec<Game>,
    finished: Option<Instant>,
    running: bool,
}

static STATE: Mutex<State> = Mutex::new(State {
    settings: Settings { folders: Vec::new(), projects: Vec::new(), online: false },
    games: Vec::new(),
    finished: None,
    running: false,
});

fn state() -> MutexGuard<'static, State> {
    STATE.lock().unwrap_or_else(|poison| poison.into_inner())
}

/// The last scan's games, right away; starts a fresh scan in the background
/// when there is none yet, the settings changed, or the last is a minute old.
pub fn find(config: &Config) -> Vec<Game> {
    let settings = Settings::from(config);
    let mut state = state();
    let stale = state.settings != settings || state.finished.is_none_or(|at| at.elapsed() > REFRESH);
    if stale && !state.running {
        state.running = true;
        state.settings = settings.clone();
        std::thread::spawn(move || {
            let games = scan(&settings);
            let mut state = self::state();
            if state.settings == settings {
                state.games = games;
                state.finished = Some(Instant::now());
            }
            state.running = false;
        });
    }
    state.games.clone()
}

/// Scans on this thread and keeps the result, for `hanami --list`.
pub fn scan_now(config: &Config) -> Vec<Game> {
    let settings = Settings::from(config);
    let games = scan(&settings);
    let mut state = state();
    state.settings = settings;
    state.games = games.clone();
    state.finished = Some(Instant::now());
    games
}

fn scan(settings: &Settings) -> Vec<Game> {
    list::refresh(settings.online);
    let list = list::current();
    let mut shipped = Vec::new();
    let mut known = Vec::new();
    for (root, depth) in places(&settings.folders) {
        walk(&root, depth, &list, &mut shipped, &mut known);
    }
    for folder in &settings.projects {
        let mut none = Vec::new();
        walk(folder, 3, &list::List { version: 1, ports: Vec::new() }, &mut shipped, &mut none);
    }
    let mut games = shipped;
    games.extend(known);
    games.extend(flatpaks(&list));
    games.extend(projects::find(&settings.projects));
    // The same port in two folders, or as Flatpak and AppImage, is one game.
    let mut seen = HashSet::new();
    games.retain(|game| seen.insert(game.name.to_lowercase()));
    games
}

/// Where to look and how deep: the settings' folders, then the usual places.
fn places(folders: &[PathBuf]) -> Vec<(PathBuf, usize)> {
    let home = dirs::home_dir().unwrap_or_default();
    let mut roots: Vec<(PathBuf, usize)> = folders.iter().map(|folder| (folder.clone(), 4)).collect();
    roots.push((home.join("Games"), 4));
    if cfg!(windows) {
        roots.push((dirs::desktop_dir().unwrap_or_else(|| home.join("Desktop")), 2));
        roots.push((PathBuf::from("C:\\Games"), 4));
        roots.push((PathBuf::from("D:\\Games"), 4));
    } else {
        roots.push((home.join("Applications"), 3));
        roots.push((home.join("AppImages"), 3));
        roots.push((PathBuf::from("/opt"), 3));
    }
    roots.push((dirs::download_dir().unwrap_or_else(|| home.join("Downloads")), 2));
    let mut seen = HashSet::new();
    roots.retain(|(root, _)| root.is_dir() && seen.insert(root.clone()));
    roots
}

/// Programs from the list and hanami-game.toml files under `root`.
fn walk(root: &Path, depth: usize, list: &list::List, shipped: &mut Vec<Game>, known: &mut Vec<Game>) {
    let entries =
        WalkDir::new(root).max_depth(depth).into_iter().filter_entry(|entry| entry.depth() == 0 || !skipped(entry));
    for entry in entries.flatten() {
        let path = entry.path();
        let Some(name) = path.file_name().and_then(|name| name.to_str()) else { continue };
        if entry.file_type().is_dir() {
            continue;
        }
        if name == SHIPPED {
            shipped.extend(read_shipped(path));
            continue;
        }
        if !runnable(path, name) {
            continue;
        }
        if let Some(port) = list.ports.iter().find(|port| port.is_program(path)) {
            known.push(Game {
                name: port.name.clone(),
                label: "port".into(),
                launch: Launch::Command {
                    program: path.to_path_buf(),
                    args: vec![],
                    dir: path.parent().map(Path::to_path_buf),
                },
                icon: None,
            });
        }
    }
}

fn skipped(entry: &DirEntry) -> bool {
    let name = entry.file_name().to_string_lossy();
    entry.file_type().is_dir() && (name.starts_with('.') || SKIP.iter().any(|skip| name.eq_ignore_ascii_case(skip)))
}

/// A file Hanami could start: executable on Linux, an .exe on Windows.
#[cfg(unix)]
fn runnable(path: &Path, _name: &str) -> bool {
    use std::os::unix::fs::PermissionsExt;
    std::fs::metadata(path).is_ok_and(|meta| meta.is_file() && meta.permissions().mode() & 0o111 != 0)
}

#[cfg(not(unix))]
fn runnable(path: &Path, _name: &str) -> bool {
    path.extension().is_some_and(|ext| ext.eq_ignore_ascii_case("exe")) && path.is_file()
}

/// Installed Flatpaks whose ids are on the list.
fn flatpaks(list: &list::List) -> Vec<Game> {
    if cfg!(windows) {
        return Vec::new();
    }
    let home = dirs::home_dir().unwrap_or_default();
    let mut games = Vec::new();
    for dir in [home.join(".local/share/flatpak/app"), PathBuf::from("/var/lib/flatpak/app")] {
        let Ok(entries) = std::fs::read_dir(dir) else { continue };
        for id in entries.flatten().filter_map(|entry| entry.file_name().into_string().ok()) {
            if let Some(port) = list.ports.iter().find(|port| port.flatpak.contains(&id)) {
                games.push(Game {
                    name: port.name.clone(),
                    label: "port".into(),
                    launch: Launch::Command { program: "flatpak".into(), args: vec!["run".into(), id], dir: None },
                    icon: None,
                });
            }
        }
    }
    games
}

/// What a port ships next to its program so Hanami knows how to start it.
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Shipped {
    name: String,
    command: String,
    #[serde(default)]
    args: Vec<String>,
    icon: Option<String>,
    label: Option<String>,
    linux: Option<Override>,
    windows: Option<Override>,
}

#[derive(Debug, Default, Deserialize)]
#[serde(deny_unknown_fields)]
struct Override {
    command: Option<String>,
    args: Option<Vec<String>>,
    icon: Option<String>,
}

fn read_shipped(path: &Path) -> Option<Game> {
    let dir = path.parent()?;
    let game = parse_shipped(&std::fs::read_to_string(path).ok()?, dir)?;
    let Launch::Command { program, .. } = &game.launch else { return None };
    program.is_file().then_some(game)
}

fn parse_shipped(text: &str, dir: &Path) -> Option<Game> {
    let shipped: Shipped = toml::from_str(text).ok()?;
    let own = if cfg!(windows) { shipped.windows } else { shipped.linux }.unwrap_or_default();
    let command = own.command.unwrap_or(shipped.command);
    if shipped.name.trim().is_empty() || command.trim().is_empty() {
        return None;
    }
    Some(Game {
        name: shipped.name,
        label: shipped.label.unwrap_or_else(|| "port".into()),
        launch: Launch::Command {
            program: dir.join(command),
            args: own.args.unwrap_or(shipped.args),
            dir: Some(dir.to_path_buf()),
        },
        icon: own.icon.or(shipped.icon).map(|icon| dir.join(icon)),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp(name: &str) -> PathBuf {
        let root = std::env::temp_dir().join(format!("hanami-ports-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).unwrap();
        root
    }

    fn make_runnable(path: &Path) {
        std::fs::write(path, "").unwrap();
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o755)).unwrap();
        }
    }

    #[test]
    fn shipped_file_is_read_relative_to_its_folder() {
        let dir = Path::new("/games/soh");
        let text = "name = \"Ship of Harkinian\"\ncommand = \"soh.elf\"\nargs = [\"--fast\"]\nicon = \"icon.png\"\n";
        let game = parse_shipped(text, dir).unwrap();
        assert_eq!((game.name.as_str(), game.label.as_str()), ("Ship of Harkinian", "port"));
        assert_eq!(
            game.launch,
            Launch::Command { program: dir.join("soh.elf"), args: vec!["--fast".into()], dir: Some(dir.to_path_buf()) }
        );
        assert_eq!(game.icon, Some(dir.join("icon.png")));

        let per_system = "name = \"X\"\ncommand = \"x\"\nlabel = \"recomp\"\n[linux]\ncommand = \"x.sh\"\n[windows]\ncommand = \"x.exe\"\nargs = [\"-w\"]\n";
        let game = parse_shipped(per_system, dir).unwrap();
        let Launch::Command { program, args, .. } = game.launch else { panic!() };
        assert_eq!(game.label, "recomp");
        if cfg!(windows) {
            assert_eq!((program, args), (dir.join("x.exe"), vec!["-w".to_string()]));
        } else {
            assert_eq!((program, args), (dir.join("x.sh"), vec![]));
        }

        assert!(parse_shipped("name = \"X\"\n", dir).is_none());
        assert!(parse_shipped("name = \"\"\ncommand = \"x\"\n", dir).is_none());
        assert!(parse_shipped("name = \"X\"\ncommand = \"x\"\nextra = 1\n", dir).is_none());
    }

    #[test]
    fn folders_are_walked_for_ports_and_shipped_games() {
        let root = temp("walk");
        let list = list::List {
            version: 1,
            ports: vec![list::Port {
                name: "OpenTTD".into(),
                linux: vec!["openttd".into()],
                windows: vec!["openttd.exe".into()],
                ..list::Port::default()
            }],
        };
        let exe = |name: &str| if cfg!(windows) { format!("{name}.exe") } else { name.to_string() };
        std::fs::create_dir_all(root.join("openttd-15")).unwrap();
        make_runnable(&root.join("openttd-15").join(exe("openttd")));
        std::fs::write(root.join("openttd-15/readme.txt"), "").unwrap();
        std::fs::create_dir_all(root.join("node_modules/x")).unwrap();
        make_runnable(&root.join("node_modules/x").join(exe("openttd")));
        std::fs::create_dir_all(root.join("mine")).unwrap();
        std::fs::write(root.join("mine").join(SHIPPED), format!("name = \"Mine\"\ncommand = \"{}\"\n", exe("mine")))
            .unwrap();
        std::fs::create_dir_all(root.join("broken")).unwrap();
        std::fs::write(root.join("broken").join(SHIPPED), "name = \"Broken\"\ncommand = \"missing\"\n").unwrap();
        if !cfg!(windows) {
            std::fs::write(root.join("openttd-15/openttd.txt"), "").unwrap();
            std::fs::create_dir_all(root.join("not-runnable")).unwrap();
            std::fs::write(root.join("not-runnable/openttd"), "").unwrap();
        }

        let (mut shipped, mut known) = (Vec::new(), Vec::new());
        walk(&root, 3, &list, &mut shipped, &mut known);
        assert!(shipped.is_empty(), "the shipped program must exist");
        assert_eq!(known.len(), 1, "{known:?}");
        assert_eq!(known[0].name, "OpenTTD");
        assert_eq!(known[0].label, "port");
        let Launch::Command { program, dir, .. } = &known[0].launch else { panic!() };
        assert_eq!(program, &root.join("openttd-15").join(exe("openttd")));
        assert_eq!(dir.as_deref(), Some(root.join("openttd-15").as_path()));

        make_runnable(&root.join("mine").join(exe("mine")));
        let (mut shipped, mut known) = (Vec::new(), Vec::new());
        walk(&root, 3, &list, &mut shipped, &mut known);
        assert_eq!(shipped.len(), 1);
        assert_eq!(shipped[0].name, "Mine");

        let (mut shipped, mut known) = (Vec::new(), Vec::new());
        walk(&root, 1, &list, &mut shipped, &mut known);
        assert!(shipped.is_empty() && known.is_empty(), "depth is respected");
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn settings_come_from_the_config_with_home_expanded() {
        let config =
            Config { folders: vec!["~/Games/ports".into()], projects: vec!["~/Projects".into()], ..Config::default() };
        let settings = Settings::from(&config);
        let home = dirs::home_dir().unwrap();
        assert_eq!(settings.folders, [home.join("Games/ports")]);
        assert_eq!(settings.projects, [home.join("Projects")]);
        assert!(settings.online);
    }
}
