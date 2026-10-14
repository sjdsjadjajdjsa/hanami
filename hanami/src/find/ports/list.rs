//! The list of known ports: one copy built into Hanami, a newer one fetched
//! from GitHub at most once a day, and whichever has the higher version wins.

use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::{Duration, Instant, SystemTime};

use serde::Deserialize;

const BUILT_IN: &str = include_str!("../../../../ports.toml");
const URL: &str = "https://raw.githubusercontent.com/sjdsjadjajdjsa/hanami/main/ports.toml";
const DAY: Duration = Duration::from_secs(24 * 60 * 60);

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct List {
    pub version: u32,
    #[serde(default, rename = "port")]
    pub ports: Vec<Port>,
}

#[derive(Debug, Clone, PartialEq, Default, Deserialize)]
pub struct Port {
    pub name: String,
    #[serde(default)]
    pub url: String,
    #[serde(default)]
    pub linux: Vec<String>,
    #[serde(default)]
    pub windows: Vec<String>,
    #[serde(default)]
    pub flatpak: Vec<String>,
    /// Files that must sit next to the program, any one of them.
    #[serde(default)]
    pub beside: Vec<String>,
}

pub fn parse(text: &str) -> Option<List> {
    toml::from_str::<List>(text).ok().filter(|list| list.version > 0)
}

/// The newest list at hand: the built-in one or the cached download.
pub fn current() -> List {
    let built_in = parse(BUILT_IN).expect("ports.toml is valid");
    let cached = cache_path().and_then(|path| std::fs::read_to_string(path).ok()).and_then(|text| parse(&text));
    newest(built_in, cached)
}

fn newest(built_in: List, cached: Option<List>) -> List {
    match cached {
        Some(cached) if cached.version > built_in.version => cached,
        _ => built_in,
    }
}

fn cache_path() -> Option<PathBuf> {
    dirs::cache_dir().map(|dir| dir.join("hanami").join("ports.toml"))
}

/// Downloads the list on its own thread when the cached copy is a day old or
/// missing; one try a day, so being offline costs nothing.
pub fn refresh(online: bool) {
    static LAST_TRY: Mutex<Option<Instant>> = Mutex::new(None);
    if !online {
        return;
    }
    let Some(path) = cache_path() else { return };
    let mut last = LAST_TRY.lock().unwrap_or_else(|poison| poison.into_inner());
    if last.is_some_and(|at| at.elapsed() < DAY) || !due(&path) {
        return;
    }
    *last = Some(Instant::now());
    std::thread::spawn(move || {
        if let Ok(text) = crate::net::get(URL)
            && parse(&text).is_some()
            && let Some(dir) = path.parent()
            && std::fs::create_dir_all(dir).is_ok()
        {
            let _ = std::fs::write(path, text);
        }
        desktop::return_memory();
    });
}

fn due(cache: &Path) -> bool {
    let Ok(modified) = std::fs::metadata(cache).and_then(|meta| meta.modified()) else { return true };
    SystemTime::now().duration_since(modified).is_ok_and(|age| age > DAY)
}

/// Shell-style file name matching, case-insensitive: `SoH-*.appimage`.
pub fn matches(pattern: &str, file_name: &str) -> bool {
    const OPTIONS: glob::MatchOptions = glob::MatchOptions {
        case_sensitive: false,
        require_literal_separator: true,
        require_literal_leading_dot: false,
    };
    glob::Pattern::new(pattern).is_ok_and(|pattern| pattern.matches_with(file_name, OPTIONS))
}

impl Port {
    /// The file names to look for on this system.
    pub fn files(&self) -> &[String] {
        if cfg!(windows) { &self.windows } else { &self.linux }
    }

    /// Whether `file` is this port's program: its name fits and, when the
    /// list asks for it, one of the `beside` files is next to it.
    pub fn is_program(&self, file: &Path) -> bool {
        let Some(name) = file.file_name().and_then(|name| name.to_str()) else { return false };
        self.files().iter().any(|pattern| matches(pattern, name))
            && (self.beside.is_empty() || self.beside.iter().any(|needed| file.with_file_name(needed).exists()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn built_in_list_is_valid_and_complete() {
        let list = parse(BUILT_IN).unwrap();
        assert!(list.ports.len() > 20);
        for port in &list.ports {
            assert!(!port.name.is_empty());
            assert!(port.url.starts_with("https://"), "{}", port.name);
            assert!(!port.linux.is_empty() || !port.flatpak.is_empty(), "{} has no Linux file", port.name);
            assert!(!port.windows.is_empty() || !port.flatpak.is_empty(), "{} has no Windows file", port.name);
            for pattern in port.linux.iter().chain(&port.windows) {
                assert!(glob::Pattern::new(pattern).is_ok(), "{pattern}");
                assert!(!pattern.contains('/'), "{pattern}");
            }
        }
        let mut names: Vec<_> = list.ports.iter().map(|port| port.name.to_lowercase()).collect();
        names.sort();
        names.dedup();
        assert_eq!(names.len(), list.ports.len(), "a port is listed twice");
    }

    #[test]
    fn names_match_without_case_and_with_versions() {
        assert!(matches("soh.appimage", "SoH.AppImage"));
        assert!(matches("SoH-*.appimage", "SoH-MacReady-Charlie-Linux.appimage"));
        assert!(matches("OpenRCT2-*.appimage", "OpenRCT2-v0.5.6-linux-x86_64.AppImage"));
        assert!(matches("openttd", "openttd"));
        assert!(!matches("openttd", "openttd.exe"));
        assert!(!matches("soh.exe", "soh.exe.bak"));
        assert!(!matches("SoH-*.appimage", "SoH-Linux.zip"));
        assert!(!matches("Starship.exe", "starship-prompt.exe"));
        assert!(!matches("[", "["));
    }

    #[test]
    fn programs_need_their_companion_files() {
        let root = std::env::temp_dir().join(format!("hanami-ports-list-{}", std::process::id()));
        std::fs::create_dir_all(&root).unwrap();
        let port = Port {
            name: "Starship".into(),
            linux: vec!["starship".into()],
            windows: vec!["starship.exe".into()],
            beside: vec!["starship.o2r".into()],
            ..Port::default()
        };
        let program = if cfg!(windows) { root.join("Starship.EXE") } else { root.join("Starship") };
        assert!(!port.is_program(&program));
        std::fs::write(root.join("starship.o2r"), "").unwrap();
        assert!(port.is_program(&program));
        assert!(!port.is_program(&root.join("other")));
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn higher_version_wins() {
        let list = |version| List { version, ports: vec![Port { name: format!("v{version}"), ..Port::default() }] };
        assert_eq!(newest(list(3), None).ports[0].name, "v3");
        assert_eq!(newest(list(3), Some(list(2))).ports[0].name, "v3");
        assert_eq!(newest(list(3), Some(list(3))).ports[0].name, "v3");
        assert_eq!(newest(list(3), Some(list(4))).ports[0].name, "v4");
        assert!(parse("version = 0\n").is_none());
        assert!(parse("ports = 1").is_none());
        assert_eq!(parse("version = 2\n[[port]]\nname = \"X\"\nextra = 1\n").unwrap().ports[0].name, "X");
    }
}
