//! Finding named icons the way the freedesktop icon theme spec says, kept to
//! what Hanami needs: application icons, one size, the user's theme and the
//! themes it inherits, hicolor last. Each folder is listed once per lookup
//! set, so a whole app menu costs a few milliseconds.

use std::cell::RefCell;
use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};

/// A set of lookups sharing their folder listings.
pub struct Lookup {
    bases: Vec<PathBuf>,
    themes: Vec<Theme>,
    listings: RefCell<HashMap<PathBuf, HashSet<String>>>,
}

struct Theme {
    dirs: Vec<Dir>,
}

struct Dir {
    paths: Vec<PathBuf>,
    /// 0 when the folder has icons of the wanted size.
    distance: u32,
}

impl Lookup {
    pub fn new(theme: &str, size: u32) -> Self {
        Self::in_bases(theme, size, bases())
    }

    /// `theme`, the themes it inherits (depth first), then hicolor.
    fn in_bases(theme: &str, size: u32, bases: Vec<PathBuf>) -> Self {
        let mut themes = Vec::new();
        let mut queue = vec![theme.to_string()];
        let mut seen = HashSet::new();
        while let Some(name) = queue.pop().or_else(|| (!seen.contains("hicolor")).then(|| "hicolor".to_string())) {
            if !seen.insert(name.clone()) {
                continue;
            }
            let Some(index) = bases.iter().map(|b| b.join(&name).join("index.theme")).find(|p| p.is_file()) else {
                continue;
            };
            let text = std::fs::read_to_string(index).unwrap_or_default();
            let (dirs, inherits) = parse_index(&text, size);
            let dirs = dirs
                .into_iter()
                .map(|(dir, distance)| Dir {
                    paths: bases.iter().map(|b| b.join(&name).join(&dir)).filter(|p| p.is_dir()).collect(),
                    distance,
                })
                .filter(|dir| !dir.paths.is_empty())
                .collect();
            themes.push(Theme { dirs });
            queue.extend(inherits.into_iter().rev());
        }
        Self { bases, themes, listings: RefCell::default() }
    }

    /// The file for `name`: exact size first, then the nearest size, theme by
    /// theme; then the unthemed icon folders and pixmaps.
    pub fn find(&self, name: &str) -> Option<PathBuf> {
        let mut listings = self.listings.borrow_mut();
        let candidates = [format!("{name}.png"), format!("{name}.svg"), format!("{name}.xpm")];
        for theme in &self.themes {
            let mut best: Option<(u32, PathBuf)> = None;
            for dir in &theme.dirs {
                if best.as_ref().is_some_and(|(distance, _)| *distance <= dir.distance) {
                    continue;
                }
                for path in &dir.paths {
                    let files = listings.entry(path.clone()).or_insert_with(|| list(path));
                    if let Some(file) = candidates.iter().find(|file| files.contains(*file)) {
                        best = Some((dir.distance, path.join(file)));
                        break;
                    }
                }
            }
            if let Some((_, path)) = best {
                return Some(path);
            }
        }
        self.bases
            .iter()
            .map(PathBuf::as_path)
            .chain([Path::new("/usr/share/pixmaps")])
            .flat_map(|dir| candidates.iter().map(move |file| dir.join(file)))
            .find(|path| path.is_file())
    }
}

fn list(dir: &Path) -> HashSet<String> {
    std::fs::read_dir(dir).into_iter().flatten().flatten().filter_map(|e| e.file_name().into_string().ok()).collect()
}

/// `$HOME/.icons`, then `icons` under the data folders (with Flatpak's exports).
fn bases() -> Vec<PathBuf> {
    let home = dirs::home_dir().unwrap_or_default();
    let data_home = std::env::var_os("XDG_DATA_HOME")
        .filter(|v| !v.is_empty())
        .map(PathBuf::from)
        .unwrap_or_else(|| home.join(".local/share"));
    let data_dirs = std::env::var("XDG_DATA_DIRS")
        .ok()
        .filter(|v| !v.is_empty())
        .unwrap_or_else(|| "/usr/local/share:/usr/share".into());
    let mut roots = vec![home.join(".icons"), data_home.join("icons")];
    roots.extend(data_dirs.split(':').filter(|d| !d.is_empty()).map(|d| Path::new(d).join("icons")));
    roots.push(home.join(".local/share/flatpak/exports/share/icons"));
    roots.push(PathBuf::from("/var/lib/flatpak/exports/share/icons"));
    let mut seen = HashSet::new();
    roots.into_iter().filter(|dir| seen.insert(dir.clone())).collect()
}

/// The application icon folders of an index.theme with how far their size is
/// from `size`, and the themes it inherits.
fn parse_index(text: &str, size: u32) -> (Vec<(String, u32)>, Vec<String>) {
    #[derive(Default)]
    struct Group {
        name: String,
        size: u32,
        min: Option<u32>,
        max: Option<u32>,
        threshold: Option<u32>,
        scale: u32,
        kind: String,
        context: Option<String>,
    }
    let mut groups: Vec<Group> = Vec::new();
    let mut inherits = Vec::new();
    for line in text.lines().map(str::trim) {
        if let Some(name) = line.strip_prefix('[').and_then(|l| l.strip_suffix(']')) {
            groups.push(Group { name: name.to_string(), scale: 1, ..Group::default() });
            continue;
        }
        let Some((key, value)) = line.split_once('=') else { continue };
        let (key, value) = (key.trim(), value.trim());
        let Some(group) = groups.last_mut() else { continue };
        if group.name == "Icon Theme" {
            if key == "Inherits" {
                inherits = value.split(',').map(str::trim).filter(|s| !s.is_empty()).map(String::from).collect();
            }
            continue;
        }
        match key {
            "Size" => group.size = value.parse().unwrap_or(0),
            "MinSize" => group.min = value.parse().ok(),
            "MaxSize" => group.max = value.parse().ok(),
            "Threshold" => group.threshold = value.parse().ok(),
            "Scale" => group.scale = value.parse().unwrap_or(1),
            "Type" => group.kind = value.to_string(),
            "Context" => group.context = Some(value.to_string()),
            _ => {}
        }
    }
    let dirs = groups
        .into_iter()
        .filter(|g| g.name != "Icon Theme" && g.size > 0 && g.scale == 1)
        .filter(|g| g.context.as_deref().is_none_or(|c| c == "Applications"))
        .map(|g| {
            let (min, max) = match g.kind.as_str() {
                "Scalable" => (g.min.unwrap_or(g.size), g.max.unwrap_or(g.size)),
                "Threshold" => {
                    let t = g.threshold.unwrap_or(2);
                    (g.size.saturating_sub(t), g.size + t)
                }
                _ => (g.size, g.size),
            };
            (g.name, min.saturating_sub(size).max(size.saturating_sub(max)))
        })
        .collect();
    (dirs, inherits)
}

#[cfg(test)]
mod tests {
    use super::*;

    const INDEX: &str = "[Icon Theme]\nName=Test\nInherits=parent,hicolor\n\n[48x48/apps]\nSize=48\nContext=Applications\nType=Fixed\n\n\
[22x22/apps]\nSize=22\nContext=Applications\n\n[scalable/apps]\nSize=64\nMinSize=16\nMaxSize=512\nType=Scalable\nContext=Applications\n\n\
[48x48/actions]\nSize=48\nContext=Actions\n\n[apps/48@2x]\nSize=48\nScale=2\nContext=Applications\n";

    #[test]
    fn index_keeps_app_folders_with_their_distance() {
        let (dirs, inherits) = parse_index(INDEX, 48);
        assert_eq!(inherits, ["parent", "hicolor"]);
        assert_eq!(dirs, [("48x48/apps".to_string(), 0), ("22x22/apps".into(), 26), ("scalable/apps".into(), 0)]);
    }

    #[test]
    fn exact_size_wins_then_nearest_then_parent_then_pixmaps() {
        let root = std::env::temp_dir().join(format!("hanami-theme-{}", std::process::id()));
        let write = |file: &str, text: &str| {
            let path = root.join(file);
            std::fs::create_dir_all(path.parent().unwrap()).unwrap();
            std::fs::write(&path, text).unwrap();
            path
        };
        write("mine/index.theme", INDEX);
        write("parent/index.theme", "[Icon Theme]\nName=P\n\n[128x128/apps]\nSize=128\nContext=Applications\n");
        let small = write("mine/22x22/apps/a.png", "");
        let exact = write("mine/48x48/apps/a.png", "");
        write("mine/scalable/apps/b.svg", "");
        let b_small = write("mine/22x22/apps/b.png", "");
        let c = write("parent/128x128/apps/c.png", "");
        let loose = write("d.png", "");

        write("hicolor/index.theme", "[Icon Theme]\nName=H\n\n[48x48/apps]\nSize=48\nContext=Applications\n");
        let e = write("hicolor/48x48/apps/e.png", "");

        let lookup = Lookup::in_bases("mine", 48, vec![root.clone()]);
        assert_eq!(lookup.themes.len(), 3);
        assert_eq!(lookup.find("a"), Some(exact));
        assert_ne!(lookup.find("a"), Some(small));
        assert_eq!(lookup.find("b"), Some(root.join("mine/scalable/apps/b.svg")));
        assert_ne!(lookup.find("b"), Some(b_small));
        assert_eq!(lookup.find("c"), Some(c));
        assert_eq!(lookup.find("d"), Some(loose));
        assert_eq!(lookup.find("e"), Some(e));
        assert_eq!(lookup.find("nothing"), None);
        std::fs::remove_dir_all(root).unwrap();
    }
}
