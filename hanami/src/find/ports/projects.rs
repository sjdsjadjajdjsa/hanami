//! Rust games in the `projects` folders: packages that use a game engine (or
//! say so with `[package.metadata.hanami]`) and have a built program.

use std::collections::HashSet;
use std::path::{Path, PathBuf};

use toml::{Table, Value};

use crate::games::{Game, Launch};

/// Game engines and frameworks on crates.io; a dependency starting with one
/// of these (`bevy`, `bevy_ecs`, `fyrox-sound`) marks a package as a game.
const ENGINES: [&str; 30] = [
    "amethyst",
    "bevy",
    "blue_engine",
    "bracket-lib",
    "bracket-terminal",
    "coffee",
    "comfy",
    "doryen-rs",
    "emerald",
    "fyrox",
    "ggez",
    "godot",
    "good-web-game",
    "kiss3d",
    "macroquad",
    "miniquad",
    "notan",
    "oxygengine",
    "piston",
    "piston_window",
    "quicksilver",
    "raylib",
    "rg3d",
    "sdl2",
    "sdl3",
    "sfml",
    "speedy2d",
    "tetra",
    "three-d",
    "turbo-genesis-sdk",
];

/// Folders never worth looking into for a project.
const SKIP: [&str; 6] = ["node_modules", "target", "vendor", ".git", ".cargo", "backup"];

pub fn find(folders: &[PathBuf]) -> Vec<Game> {
    let mut games = Vec::new();
    for folder in folders {
        for project in projects(folder) {
            games.extend(analyse(&project));
        }
    }
    games
}

/// Folders with a Cargo.toml directly in `folder` or one level down.
fn projects(folder: &Path) -> Vec<PathBuf> {
    fn children(dir: &Path) -> Vec<PathBuf> {
        let Ok(entries) = std::fs::read_dir(dir) else { return Vec::new() };
        let mut dirs: Vec<PathBuf> = entries
            .flatten()
            .map(|entry| entry.path())
            .filter(|path| path.is_dir() && !path.file_name().is_some_and(|name| skipped(&name.to_string_lossy())))
            .collect();
        dirs.sort();
        dirs
    }
    let mut found = Vec::new();
    for child in children(folder) {
        if child.join("Cargo.toml").is_file() {
            found.push(child);
        } else {
            found.extend(children(&child).into_iter().filter(|dir| dir.join("Cargo.toml").is_file()));
        }
    }
    found
}

fn skipped(name: &str) -> bool {
    name.starts_with('.')
        || SKIP.iter().any(|skip| name.eq_ignore_ascii_case(skip))
        || name.to_lowercase().contains("backup")
}

fn read_manifest(dir: &Path) -> Option<Table> {
    toml::from_str(&std::fs::read_to_string(dir.join("Cargo.toml")).ok()?).ok()
}

/// The games in one project: a single package, or every package of a workspace.
pub fn analyse(root: &Path) -> Vec<Game> {
    let Some(manifest) = read_manifest(root) else { return Vec::new() };
    let workspace = manifest.get("workspace").and_then(Value::as_table);
    let workspace_engines: HashSet<String> = workspace
        .and_then(|ws| ws.get("dependencies"))
        .and_then(Value::as_table)
        .into_iter()
        .flat_map(|deps| deps.iter())
        .filter(|(name, dep)| is_engine(name, dep))
        .map(|(name, _)| name.clone())
        .collect();
    let target = target_dir(root);
    let script = script(root);

    let mut packages: Vec<(PathBuf, Table)> = Vec::new();
    if manifest.contains_key("package") {
        packages.push((root.to_path_buf(), manifest.clone()));
    }
    if let Some(workspace) = workspace {
        for dir in members(root, workspace) {
            if dir != root
                && let Some(manifest) = read_manifest(&dir)
            {
                packages.push((dir, manifest));
            }
        }
    }

    let mut games = Vec::new();
    for (dir, manifest) in packages {
        let Some(package) = manifest.get("package").and_then(Value::as_table) else { continue };
        let Some(name) = package.get("name").and_then(Value::as_str) else { continue };
        let metadata = package.get("metadata").and_then(|meta| meta.get("hanami")).and_then(Value::as_table);
        if metadata.is_none() && !uses_engine(&manifest, &workspace_engines) {
            continue;
        }
        let bins = chosen_bins(&manifest, &dir, name);
        for bin in &bins {
            let Some(program) = built(&target, bin) else { continue };
            let readable = if bins.len() == 1 { readable_name(name) } else { readable_name(bin) };
            let shown = metadata.and_then(|meta| meta.get("name")).and_then(Value::as_str).filter(|_| bins.len() == 1);
            let args = metadata
                .and_then(|meta| meta.get("args"))
                .and_then(Value::as_array)
                .map(|args| args.iter().filter_map(Value::as_str).map(String::from).collect())
                .unwrap_or_default();
            let icon = metadata.and_then(|meta| meta.get("icon")).and_then(Value::as_str).map(|icon| dir.join(icon));
            let launch = match &script {
                Some(script) if bins.len() == 1 => {
                    Launch::Command { program: script.clone(), args: vec![], dir: Some(root.to_path_buf()) }
                }
                _ => Launch::Command { program, args, dir: Some(root.to_path_buf()) },
            };
            games.push(Game { name: shown.map(String::from).unwrap_or(readable), label: "rust".into(), launch, icon });
        }
    }
    games
}

/// Member folders of a workspace, with `crates/*` style globs expanded.
fn members(root: &Path, workspace: &Table) -> Vec<PathBuf> {
    let list = |key: &str| -> Vec<String> {
        workspace
            .get(key)
            .and_then(Value::as_array)
            .map(|items| items.iter().filter_map(Value::as_str).map(String::from).collect())
            .unwrap_or_default()
    };
    let excluded: Vec<PathBuf> = list("exclude").iter().map(|member| root.join(member)).collect();
    let mut dirs = Vec::new();
    for member in list("members") {
        let pattern = root.join(&member);
        let Some(pattern) = pattern.to_str() else { continue };
        let Ok(paths) = glob::glob(pattern) else { continue };
        dirs.extend(paths.flatten().filter(|dir| dir.join("Cargo.toml").is_file() && !excluded.contains(dir)));
    }
    dirs.sort();
    dirs.dedup();
    dirs
}

fn is_engine(name: &str, dep: &Value) -> bool {
    // `engine = { package = "bevy", ... }` renames a dependency.
    let crate_name = dep.get("package").and_then(Value::as_str).unwrap_or(name);
    ENGINES.iter().any(|engine| {
        crate_name == *engine || crate_name.strip_prefix(engine).is_some_and(|rest| rest.starts_with(['_', '-']))
    })
}

/// Whether the package depends on an engine, directly or through the workspace.
fn uses_engine(manifest: &Table, workspace_engines: &HashSet<String>) -> bool {
    let tables = manifest.get("dependencies").into_iter().chain(
        manifest
            .get("target")
            .and_then(Value::as_table)
            .into_iter()
            .flat_map(|targets| targets.values())
            .filter_map(|target| target.get("dependencies")),
    );
    tables.filter_map(Value::as_table).flatten().any(|(name, dep)| {
        let from_workspace = dep.get("workspace").and_then(Value::as_bool) == Some(true);
        if from_workspace { workspace_engines.contains(name) } else { is_engine(name, dep) }
    })
}

/// The program to offer: `default-run`, else the one named like the package,
/// else the only one; several programs without a default are all offered.
fn chosen_bins(manifest: &Table, dir: &Path, package: &str) -> Vec<String> {
    let package_table = manifest.get("package").and_then(Value::as_table);
    if let Some(default) = package_table.and_then(|p| p.get("default-run")).and_then(Value::as_str) {
        return vec![default.to_string()];
    }
    let mut bins: Vec<String> = Vec::new();
    for bin in manifest.get("bin").and_then(Value::as_array).into_iter().flatten() {
        if let Some(name) = bin.get("name").and_then(Value::as_str) {
            bins.push(name.to_string());
        }
    }
    let autobins = package_table.and_then(|p| p.get("autobins")).and_then(Value::as_bool).unwrap_or(true);
    if autobins {
        if dir.join("src/main.rs").is_file() {
            bins.push(package.to_string());
        }
        if let Ok(entries) = std::fs::read_dir(dir.join("src/bin")) {
            for path in entries.flatten().map(|entry| entry.path()) {
                if (path.extension().is_some_and(|ext| ext == "rs") || path.join("main.rs").is_file())
                    && let Some(stem) = path.file_stem().and_then(|stem| stem.to_str())
                {
                    bins.push(stem.to_string());
                }
            }
        }
    }
    bins.sort();
    bins.dedup();
    if bins.iter().any(|bin| bin == package) {
        return vec![package.to_string()];
    }
    bins
}

/// Cargo's output folder: `target`, unless `.cargo/config.toml` says otherwise.
fn target_dir(root: &Path) -> PathBuf {
    let configured = std::fs::read_to_string(root.join(".cargo/config.toml"))
        .ok()
        .and_then(|text| toml::from_str::<Table>(&text).ok())
        .and_then(|config| config.get("build")?.get("target-dir")?.as_str().map(PathBuf::from));
    match configured {
        Some(dir) => root.join(dir),
        None => root.join("target"),
    }
}

/// The built program, release first, then debug.
fn built(target: &Path, bin: &str) -> Option<PathBuf> {
    let file = if cfg!(windows) { format!("{bin}.exe") } else { bin.to_string() };
    ["release", "debug"].iter().map(|profile| target.join(profile).join(&file)).find(|path| path.is_file())
}

/// A `play.sh` (Linux) or `play.bat` (Windows) next to the Cargo.toml starts
/// the game the way its maker meant.
fn script(root: &Path) -> Option<PathBuf> {
    let names: &[&str] = if cfg!(windows) { &["play.bat", "play.cmd"] } else { &["play.sh"] };
    std::fs::read_dir(root).ok()?.flatten().map(|entry| entry.path()).find(|path| {
        path.is_file()
            && path.file_name().is_some_and(|name| names.iter().any(|want| name.eq_ignore_ascii_case(want)))
            && runnable(path)
    })
}

#[cfg(unix)]
fn runnable(path: &Path) -> bool {
    use std::os::unix::fs::PermissionsExt;
    std::fs::metadata(path).is_ok_and(|meta| meta.permissions().mode() & 0o111 != 0)
}

#[cfg(not(unix))]
fn runnable(_path: &Path) -> bool {
    true
}

/// `skate-game` becomes `Skate Game`, `pixel-gun-3d-rs` becomes `Pixel Gun 3D`.
pub fn readable_name(package: &str) -> String {
    let mut words: Vec<&str> = package.split(['-', '_']).filter(|word| !word.is_empty()).collect();
    if words.len() > 1 && matches!(words.last(), Some(&"rs" | &"rust")) {
        words.pop();
    }
    words
        .iter()
        .map(|word| {
            let mut chars = word.chars();
            match chars.next() {
                Some(first) if first.is_ascii_digit() => word.to_uppercase(),
                Some(first) => first.to_uppercase().chain(chars).collect(),
                None => String::new(),
            }
        })
        .collect::<Vec<_>>()
        .join(" ")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn write(root: &Path, file: &str, text: &str) {
        let path = root.join(file);
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(path, text).unwrap();
    }

    fn temp(name: &str) -> PathBuf {
        let root = std::env::temp_dir().join(format!("hanami-projects-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).unwrap();
        root
    }

    fn exe(name: &str) -> String {
        if cfg!(windows) { format!("{name}.exe") } else { name.to_string() }
    }

    #[test]
    fn names_become_readable() {
        assert_eq!(readable_name("skate-game"), "Skate Game");
        assert_eq!(readable_name("pixel-gun-3d-rs"), "Pixel Gun 3D");
        assert_eq!(readable_name("my_game_rust"), "My Game");
        assert_eq!(readable_name("rs"), "Rs");
        assert_eq!(readable_name("rhythm"), "Rhythm");
    }

    #[test]
    fn engines_are_recognised_by_prefix_and_rename() {
        let plain = Value::String("1".into());
        assert!(is_engine("bevy", &plain));
        assert!(is_engine("bevy_ecs", &plain));
        assert!(is_engine("fyrox-sound", &plain));
        assert!(is_engine("engine", &toml::from_str::<Table>("package = \"macroquad\"").unwrap().into()));
        assert!(!is_engine("bevyond", &plain));
        assert!(!is_engine("slint", &plain));
        assert!(!is_engine("serde", &plain));
    }

    #[test]
    fn single_package_needs_an_engine_and_a_built_program() {
        let root = temp("single");
        write(&root, "Cargo.toml", "[package]\nname = \"pixel-gun-3d-rs\"\n[dependencies]\nbevy = \"0.20\"\n");
        write(&root, "src/main.rs", "");
        assert!(analyse(&root).is_empty(), "not built yet");

        write(&root, &format!("target/debug/{}", exe("pixel-gun-3d-rs")), "");
        let games = analyse(&root);
        assert_eq!(games.len(), 1);
        assert_eq!((games[0].name.as_str(), games[0].label.as_str()), ("Pixel Gun 3D", "rust"));
        assert_eq!(
            games[0].launch,
            Launch::Command {
                program: root.join("target/debug").join(exe("pixel-gun-3d-rs")),
                args: vec![],
                dir: Some(root.clone())
            }
        );

        write(&root, &format!("target/release/{}", exe("pixel-gun-3d-rs")), "");
        let Launch::Command { program, .. } = &analyse(&root)[0].launch else { panic!() };
        assert_eq!(program, &root.join("target/release").join(exe("pixel-gun-3d-rs")), "release wins");

        write(&root, "Cargo.toml", "[package]\nname = \"pixel-gun-3d-rs\"\n[dependencies]\nserde = \"1\"\n");
        assert!(analyse(&root).is_empty(), "no engine");
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn metadata_names_the_game_without_an_engine() {
        let root = temp("metadata");
        write(
            &root,
            "Cargo.toml",
            "[package]\nname = \"tool\"\n[package.metadata.hanami]\nname = \"Skate 3\"\nargs = [\"--fast\"]\nicon = \"art/icon.png\"\n",
        );
        write(&root, "src/main.rs", "");
        write(&root, &format!("target/release/{}", exe("tool")), "");
        let games = analyse(&root);
        assert_eq!(games[0].name, "Skate 3");
        assert_eq!(games[0].icon, Some(root.join("art/icon.png")));
        let Launch::Command { args, .. } = &games[0].launch else { panic!() };
        assert_eq!(args, &["--fast"]);
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn workspaces_follow_members_default_run_and_scripts() {
        let root = temp("workspace");
        write(
            &root,
            "Cargo.toml",
            "[workspace]\nmembers = [\"crates/*\"]\n[workspace.dependencies]\nbevy = \"0.20\"\nserde = \"1\"\n",
        );
        write(
            &root,
            "crates/skate-game/Cargo.toml",
            "[package]\nname = \"skate-game\"\ndefault-run = \"skate3rust\"\n[[bin]]\nname = \"skate3rust\"\n[[bin]]\nname = \"skate3-tools\"\n[dependencies]\nbevy = { workspace = true }\n",
        );
        write(
            &root,
            "crates/skate-core/Cargo.toml",
            "[package]\nname = \"skate-core\"\n[dependencies]\nserde = { workspace = true }\n",
        );
        write(&root, "crates/skate-core/src/main.rs", "");
        write(&root, &format!("target/release/{}", exe("skate-core")), "");
        assert!(analyse(&root).is_empty(), "default-run not built, core has no engine");

        write(&root, &format!("target/release/{}", exe("skate3rust")), "");
        write(&root, &format!("target/release/{}", exe("skate3-tools")), "");
        let games = analyse(&root);
        assert_eq!(games.len(), 1);
        assert_eq!(games[0].name, "Skate Game");
        let Launch::Command { program, dir, .. } = &games[0].launch else { panic!() };
        assert_eq!(program, &root.join("target/release").join(exe("skate3rust")));
        assert_eq!(dir.as_deref(), Some(root.as_path()), "runs from the workspace root, like cargo run");

        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            write(&root, "play.sh", "#!/bin/sh\n");
            assert_eq!(analyse(&root)[0].launch, games[0].launch, "a script that can't run is ignored");
            std::fs::set_permissions(root.join("play.sh"), std::fs::Permissions::from_mode(0o755)).unwrap();
            let Launch::Command { program, dir, .. } = &analyse(&root)[0].launch else { panic!() };
            assert_eq!(program, &root.join("play.sh"));
            assert_eq!(dir.as_deref(), Some(root.as_path()));
        }
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn several_programs_without_a_default_are_all_offered_by_their_names() {
        let root = temp("bins");
        write(&root, "Cargo.toml", "[package]\nname = \"arcade\"\n[dependencies]\nmacroquad = \"0.4\"\n");
        write(&root, "src/bin/pong.rs", "");
        write(&root, "src/bin/space_invaders/main.rs", "");
        write(&root, &format!("target/debug/{}", exe("pong")), "");
        write(&root, &format!("target/debug/{}", exe("space_invaders")), "");
        let names: Vec<_> = analyse(&root).into_iter().map(|game| game.name).collect();
        assert_eq!(names, ["Pong", "Space Invaders"]);

        write(&root, "src/main.rs", "");
        write(&root, &format!("target/debug/{}", exe("arcade")), "");
        let names: Vec<_> = analyse(&root).into_iter().map(|game| game.name).collect();
        assert_eq!(names, ["Arcade"], "the program named like the package wins");
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn projects_are_found_two_levels_down_and_junk_is_skipped() {
        let root = temp("folders");
        write(&root, "a/Cargo.toml", "");
        write(&root, "group/b/Cargo.toml", "");
        write(&root, "group/node_modules/c/Cargo.toml", "");
        write(&root, "target/d/Cargo.toml", "");
        write(&root, "a-backup/Cargo.toml", "");
        write(&root, ".hidden/Cargo.toml", "");
        write(&root, "notes.txt", "");
        assert_eq!(projects(&root), [root.join("a"), root.join("group/b")]);
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn target_dir_follows_cargo_config() {
        let root = temp("target");
        assert_eq!(target_dir(&root), root.join("target"));
        write(&root, ".cargo/config.toml", "[build]\ntarget-dir = \"out\"\n");
        assert_eq!(target_dir(&root), root.join("out"));
        std::fs::remove_dir_all(root).unwrap();
    }
}
