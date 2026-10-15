//! Minecraft instances from Prism Launcher and the launchers it grew out of
//! (PolyMC, MultiMC). Each instance is its own row and starts through its
//! launcher, which handles the Microsoft login.

use std::collections::HashMap;
use std::path::{Path, PathBuf};

use serde::Deserialize;

use crate::config::{Config, expand_home};
use crate::games::{Game, Launch, key};

const PRISM_FLATPAK: &str = "org.prismlauncher.PrismLauncher";
const POLYMC_FLATPAK: &str = "org.polymc.PolyMC";

/// One launcher's data folder and how to start its instances.
#[derive(Debug, Clone, PartialEq)]
struct Root {
    /// "Prism", "Prism Flatpak", "MultiMC": tells same-named instances apart.
    title: String,
    data: PathBuf,
    /// The launcher's own settings file in `data`.
    settings: &'static str,
    program: PathBuf,
    /// Arguments before `--launch <id>`, like `run <flatpak id>`.
    args: Vec<String>,
    /// The launcher's icon name in the icon theme, for instances without their own.
    icon: &'static str,
}

pub fn find(config: &Config) -> Vec<Game> {
    let folders: Vec<PathBuf> = config.folders.iter().map(|folder| expand_home(folder)).collect();
    let places = places(&folders);
    let mut names = HashMap::new();
    let mut games = Vec::new();
    for root in roots(&places) {
        let usable = runnable(&root);
        let found = instances(&root);
        if !usable && !found.is_empty() {
            super::report(&root.title, format!("found its instances but not {}", root.program.display()));
        }
        if found.is_empty() {
            continue;
        }
        // Every launcher with instances takes part in naming, started or not,
        // so a row keeps its name when another launcher is removed.
        let launcher = unique(&mut names, launcher_name(&root.title), &root.title, &root.title);
        let count = found.len();
        let mut rows = vec![Game {
            name: launcher.clone(),
            label: if count == 1 { "1 instance".into() } else { format!("{count} instances") },
            launch: Launch::Command {
                program: root.program.clone(),
                args: root.args.clone(),
                dir: None,
                env: Vec::new(),
            },
            icon: (!root.icon.is_empty()).then(|| PathBuf::from(root.icon)),
            group: None,
        }];
        for (id, mut game) in found {
            game.name = unique(&mut names, game.name, &root.title, &id);
            game.group = Some(launcher.clone());
            rows.push(game);
        }
        if usable {
            games.extend(rows);
        }
    }
    #[cfg(target_os = "linux")]
    if games.iter().any(|game| game.icon.as_ref().is_some_and(|icon| icon.is_relative())) {
        let theme = super::icon_theme::Lookup::new(&super::apps::icon_theme(), 48);
        for game in &mut games {
            if let Some(name) = game.icon.take_if(|icon| icon.is_relative()) {
                game.icon = name.to_str().and_then(|name| theme.find(name));
            }
        }
    }
    #[cfg(not(target_os = "linux"))]
    for game in &mut games {
        game.icon.take_if(|icon| icon.is_relative());
    }
    games
}

/// The launcher's row: "Prism Launcher", "Prism Launcher (Flatpak)".
fn launcher_name(title: &str) -> String {
    match title.split_once(' ') {
        Some((name, kind)) => format!("{} ({kind})", if name == "Prism" { "Prism Launcher" } else { name }),
        None if title == "Prism" => "Prism Launcher".into(),
        None => title.into(),
    }
}

/// `name` if free; when another launcher has it, `name (launcher)`; when
/// the same launcher has it (a copied instance), `name (folder)`. `names`
/// remembers which launcher holds each name.
fn unique(names: &mut HashMap<String, String>, name: String, title: &str, id: &str) -> String {
    let mut candidates = vec![name.clone()];
    if names.get(&key(&name)).is_some_and(|holder| holder != title) {
        candidates.push(format!("{name} ({title})"));
    }
    candidates.push(format!("{name} ({id})"));
    candidates.push(format!("{name} ({title} {id})"));
    for candidate in candidates {
        if let std::collections::hash_map::Entry::Vacant(free) = names.entry(key(&candidate)) {
            free.insert(title.to_owned());
            return candidate;
        }
    }
    name
}

/// Where portable launchers and Prism's AppImage are looked for: the
/// `folders` setting and the usual places, each with one level below it.
fn places(folders: &[PathBuf]) -> Vec<PathBuf> {
    let home = dirs::home_dir().unwrap_or_default();
    let mut places: Vec<PathBuf> = folders.to_vec();
    places.extend([home.clone(), home.join("Games"), home.join("Applications"), home.join("AppImages")]);
    places.extend(dirs::download_dir());
    places.extend(dirs::desktop_dir());
    if cfg!(windows) {
        places.extend(["C:\\Games", "D:\\Games", "C:\\MultiMC"].map(PathBuf::from));
    } else {
        places.push(PathBuf::from("/opt"));
    }
    let mut all = Vec::new();
    for place in places {
        let below = children(&place);
        all.push(place);
        all.extend(below);
    }
    let mut seen = std::collections::HashSet::new();
    all.retain(|place| seen.insert(place.clone()));
    all
}

/// The folders in `dir`, without hidden ones and links, which can lead to
/// slow network mounts.
fn children(dir: &Path) -> Vec<PathBuf> {
    let Ok(entries) = std::fs::read_dir(dir) else { return Vec::new() };
    entries
        .flatten()
        .filter(|entry| !entry.file_name().to_string_lossy().starts_with('.'))
        .filter(|entry| entry.file_type().is_ok_and(|kind| kind.is_dir()))
        .map(|entry| entry.path())
        .collect()
}

/// The installed launchers, then portable ones (a folder with the launcher's
/// settings file and program side by side) in `places`.
fn roots(places: &[PathBuf]) -> Vec<Root> {
    let mut roots = installed();
    // Prism's AppImage keeps its data where the package does, but isn't on the PATH.
    if let Some(native) = roots.iter_mut().find(|root| root.program == Path::new("prismlauncher"))
        && !runnable(native)
        && let Some(appimage) = appimage(places)
    {
        native.program = appimage;
    }
    for place in places {
        if let Some(root) = portable(place)
            && !roots.iter().any(|known| known.data == root.data)
        {
            roots.push(root);
        }
    }
    roots.retain(|root| root.data.join(root.settings).is_file() || root.data.join("instances").is_dir());
    roots
}

/// A Prism Launcher AppImage, like `PrismLauncher-Linux-x86_64.AppImage`.
fn appimage(places: &[PathBuf]) -> Option<PathBuf> {
    places.iter().flat_map(|place| std::fs::read_dir(place).into_iter().flatten().flatten()).find_map(|entry| {
        let name = entry.file_name().to_string_lossy().to_lowercase();
        (name.starts_with("prismlauncher") && name.ends_with(".appimage") && entry.path().is_file())
            .then(|| entry.path())
    })
}

/// Whether the launcher is still there: a launcher's data folder outlives
/// its uninstall.
fn runnable(root: &Root) -> bool {
    if root.program == Path::new("flatpak") {
        let Some(id) = root.args.get(1) else { return false };
        let user = dirs::data_dir().unwrap_or_default().join("flatpak/app");
        return [user, PathBuf::from("/var/lib/flatpak/app")].iter().any(|apps| apps.join(id).is_dir());
    }
    if root.program.components().count() > 1 {
        return root.program.is_file();
    }
    std::env::var_os("PATH")
        .is_some_and(|path| std::env::split_paths(&path).any(|dir| dir.join(&root.program).is_file()))
}

/// Prism and PolyMC as installed by a package, the Windows installer or Flatpak.
fn installed() -> Vec<Root> {
    let mut roots = Vec::new();
    let Some(data) = dirs::data_dir() else { return roots };
    let root = |title: &str, data: PathBuf, settings, program: PathBuf, args: &[&str], icon| Root {
        title: title.into(),
        data,
        settings,
        program,
        args: args.iter().map(|arg| arg.to_string()).collect(),
        icon,
    };
    if cfg!(windows) {
        let local = dirs::data_local_dir().unwrap_or_default();
        let program = [local.join("Programs/PrismLauncher"), PathBuf::from("C:\\Program Files\\PrismLauncher")]
            .into_iter()
            .map(|dir| dir.join("prismlauncher.exe"))
            .find(|exe| exe.is_file())
            .unwrap_or_else(|| "prismlauncher.exe".into());
        roots.push(root("Prism", data.join("PrismLauncher"), "prismlauncher.cfg", program, &[], ""));
        return roots;
    }
    let flatpak = dirs::home_dir().unwrap_or_default().join(".var/app");
    roots.push(root(
        "Prism",
        data.join("PrismLauncher"),
        "prismlauncher.cfg",
        "prismlauncher".into(),
        &[],
        PRISM_FLATPAK,
    ));
    roots.push(root(
        "Prism Flatpak",
        flatpak.join(PRISM_FLATPAK).join("data/PrismLauncher"),
        "prismlauncher.cfg",
        "flatpak".into(),
        &["run", PRISM_FLATPAK],
        PRISM_FLATPAK,
    ));
    roots.push(root("PolyMC", data.join("PolyMC"), "polymc.cfg", "polymc".into(), &[], POLYMC_FLATPAK));
    roots.push(root(
        "PolyMC Flatpak",
        flatpak.join(POLYMC_FLATPAK).join("data/PolyMC"),
        "polymc.cfg",
        "flatpak".into(),
        &["run", POLYMC_FLATPAK],
        POLYMC_FLATPAK,
    ));
    // The AUR's multimc-bin keeps its data here and puts `multimc` on the PATH.
    roots.push(root("MultiMC", data.join("multimc"), "multimc.cfg", "multimc".into(), &[], "multimc"));
    roots
}

/// A portable launcher: its settings file next to its program.
fn portable(folder: &Path) -> Option<Root> {
    const KINDS: [(&str, &str, &str, &[&str]); 3] = [
        (
            "Prism portable",
            "prismlauncher.cfg",
            PRISM_FLATPAK,
            &["prismlauncher.exe", "PrismLauncher", "bin/prismlauncher"],
        ),
        ("PolyMC portable", "polymc.cfg", POLYMC_FLATPAK, &["polymc.exe", "PolyMC", "bin/polymc"]),
        ("MultiMC", "multimc.cfg", "multimc", &["MultiMC.exe", "MultiMC", "bin/MultiMC"]),
    ];
    KINDS.iter().find_map(|&(title, settings, icon, programs)| {
        if !folder.join(settings).is_file() {
            return None;
        }
        let program = programs.iter().map(|program| folder.join(program)).find(|path| path.is_file())?;
        Some(Root { title: title.into(), data: folder.to_path_buf(), settings, program, args: Vec::new(), icon })
    })
}

/// A folder setting from the launcher's settings file, relative to its data folder.
fn folder(root: &Root, setting: &str, default: &str) -> PathBuf {
    let text = std::fs::read_to_string(root.data.join(root.settings)).unwrap_or_default();
    let value = ini_value(&text, setting).filter(|value| !value.is_empty()).unwrap_or_else(|| default.into());
    root.data.join(value)
}

/// Every instance under the root, with its folder name (the launcher's id for it).
fn instances(root: &Root) -> Vec<(String, Game)> {
    let dir = folder(root, "InstanceDir", "instances");
    let icons = folder(root, "IconsDir", "icons");
    let Ok(entries) = std::fs::read_dir(&dir) else { return Vec::new() };
    let mut found: Vec<(String, Game)> = entries
        .flatten()
        .filter_map(|entry| {
            let id = entry.file_name().to_str()?.to_owned();
            let text = std::fs::read_to_string(entry.path().join("instance.cfg")).ok()?;
            Some((id.clone(), instance(root, &id, &text, &entry.path(), &icons)))
        })
        .collect();
    found.sort_by(|a, b| a.0.cmp(&b.0));
    found
}

fn instance(root: &Root, id: &str, cfg: &str, folder: &Path, icons: &Path) -> Game {
    let pack = std::fs::read_to_string(folder.join("mmc-pack.json")).ok().and_then(|text| pack(&text));
    let version = pack.as_ref().map(|(version, _)| version.clone()).or_else(|| ini_value(cfg, "IntendedVersion"));
    let mut name = ini_value(cfg, "name").filter(|name| !name.trim().is_empty()).unwrap_or_else(|| id.into());
    // New instances are named after their Minecraft version.
    if version.as_deref() == Some(name.as_str()) {
        name = format!("Minecraft {name}");
    }
    let loader = pack.and_then(|(_, loader)| loader).unwrap_or("minecraft");
    let label = version.map_or_else(|| loader.to_string(), |version| format!("{loader} {version}"));
    let icon = ini_value(cfg, "iconKey")
        .and_then(|key| icon_file(icons, &key))
        .or_else(|| (!root.icon.is_empty()).then(|| PathBuf::from(root.icon)));
    let mut args = root.args.clone();
    args.extend(["--launch".into(), id.into()]);
    Game {
        group: None,
        name,
        label,
        launch: Launch::Command { program: root.program.clone(), args, dir: None, env: Vec::new() },
        icon,
    }
}

/// A custom icon: the launcher keeps it in its icons folder under its key.
fn icon_file(icons: &Path, key: &str) -> Option<PathBuf> {
    if key.is_empty() || key.contains(['/', '\\']) {
        return None;
    }
    ["png", "svg", "jpg", "jpeg", "ico", "gif"]
        .iter()
        .map(|ext| icons.join(format!("{key}.{ext}")))
        .find(|path| path.is_file())
}

#[derive(Deserialize)]
struct Pack {
    #[serde(default)]
    components: Vec<Component>,
}

#[derive(Deserialize)]
struct Component {
    uid: String,
    #[serde(default)]
    version: Option<String>,
}

/// The Minecraft version and mod loader from an instance's mmc-pack.json.
fn pack(text: &str) -> Option<(String, Option<&'static str>)> {
    let pack: Pack = serde_json::from_str(text).ok()?;
    let version = pack.components.iter().find(|c| c.uid == "net.minecraft")?.version.clone()?;
    let loader = pack.components.iter().find_map(|c| match c.uid.as_str() {
        "net.neoforged" => Some("neoforge"),
        "net.minecraftforge" => Some("forge"),
        "net.fabricmc.fabric-loader" => Some("fabric"),
        "org.quiltmc.quilt-loader" => Some("quilt"),
        "com.mumfrey.liteloader" => Some("liteloader"),
        _ => None,
    });
    Some((version, loader))
}

/// `key` from an instance.cfg or launcher settings file, in any group. Prism
/// writes them through Qt, which quotes values with commas or edge spaces;
/// MultiMC wrote them with backslash escapes.
fn ini_value(text: &str, key: &str) -> Option<String> {
    text.lines().find_map(|line| {
        let (name, value) = line.split_once('=')?;
        (name.trim() == key).then(|| unescape(value.trim()))
    })
}

fn unescape(value: &str) -> String {
    let value = value.strip_prefix('"').and_then(|v| v.strip_suffix('"')).unwrap_or(value);
    let mut out = String::with_capacity(value.len());
    let mut chars = value.chars();
    while let Some(c) = chars.next() {
        if c != '\\' {
            out.push(c);
            continue;
        }
        match chars.next() {
            Some('n') => out.push('\n'),
            Some('t') => out.push('\t'),
            // Qt 5 writes characters outside ASCII as \x and hex digits.
            Some('x') => {
                let digits: String = chars.clone().take_while(char::is_ascii_hexdigit).take(4).collect();
                match u32::from_str_radix(&digits, 16).ok().and_then(char::from_u32) {
                    Some(c) => {
                        out.push(c);
                        chars.nth(digits.len() - 1);
                    }
                    None => out.push('x'),
                }
            }
            Some(other) => out.push(other),
            None => out.push('\\'),
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("hanami-prism-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    fn write(path: PathBuf, text: &str) {
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(path, text).unwrap();
    }

    fn root(data: &Path, title: &str, program: &str, args: &[&str]) -> Root {
        Root {
            title: title.into(),
            data: data.to_path_buf(),
            settings: "prismlauncher.cfg",
            program: program.into(),
            args: args.iter().map(|arg| arg.to_string()).collect(),
            icon: PRISM_FLATPAK,
        }
    }

    fn pack(minecraft: &str, loader: Option<&str>) -> String {
        let loader = loader.map(|uid| format!(r#",{{"uid":"{uid}","version":"0.16.5"}}"#)).unwrap_or_default();
        format!(
            r#"{{"formatVersion":1,"components":[{{"uid":"org.lwjgl3","version":"3.3.3"}},{{"uid":"net.minecraft","version":"{minecraft}"}}{loader}]}}"#
        )
    }

    #[test]
    fn instances_become_games_that_start_through_the_launcher() {
        let data = temp("layout");
        write(data.join("prismlauncher.cfg"), "[General]\nInstanceDir=packs\nIconsDir=my icons\n");
        write(data.join("packs/26.3/instance.cfg"), "[General]\nInstanceType=OneSix\nname=26.3\n");
        write(data.join("packs/26.3/mmc-pack.json"), &pack("26.3", None));
        write(
            data.join("packs/Fabulous/instance.cfg"),
            "[General]\nname=\"Fabric, with \\\"friends\\\"\"\niconKey=creeper\n",
        );
        write(data.join("packs/Fabulous/mmc-pack.json"), &pack("1.21.1", Some("net.fabricmc.fabric-loader")));
        write(data.join("my icons/creeper.png"), "");
        write(data.join("packs/_LAUNCHER_TEMP/half/instance.cfg"), "name=half\n");
        write(data.join("packs/old/instance.cfg"), "name=Old one\nIntendedVersion=1.7.10\niconKey=grass\n");
        write(data.join("instances/elsewhere/instance.cfg"), "name=Not here\n");

        let found = instances(&root(&data, "Prism", "prismlauncher", &[]));
        let rows: Vec<(&str, &str, &str)> =
            found.iter().map(|(id, game)| (id.as_str(), game.name.as_str(), game.label.as_str())).collect();
        assert_eq!(
            rows,
            [
                ("26.3", "Minecraft 26.3", "minecraft 26.3"),
                ("Fabulous", "Fabric, with \"friends\"", "fabric 1.21.1"),
                ("old", "Old one", "minecraft 1.7.10"),
            ]
        );
        let Launch::Command { program, args, .. } = &found[0].1.launch else { panic!() };
        assert_eq!(
            (program, args.as_slice()),
            (&PathBuf::from("prismlauncher"), ["--launch", "26.3"].map(String::from).as_slice())
        );
        assert_eq!(found[1].1.icon, Some(data.join("my icons/creeper.png")));
        assert_eq!(found[2].1.icon, Some(PathBuf::from(PRISM_FLATPAK)), "built-in icons fall back to the launcher's");
        std::fs::remove_dir_all(data).unwrap();
    }

    #[test]
    fn flatpak_instances_run_through_flatpak() {
        let data = temp("flatpak");
        write(data.join("instances/My Pack/instance.cfg"), "[General]\nname=My Pack\n");
        write(data.join("instances/My Pack/mmc-pack.json"), &pack("1.20.1", Some("net.neoforged")));
        let found = instances(&root(&data, "Prism Flatpak", "flatpak", &["run", PRISM_FLATPAK]));
        let Launch::Command { program, args, .. } = &found[0].1.launch else { panic!() };
        assert_eq!(program, &PathBuf::from("flatpak"));
        assert_eq!(args, &["run", PRISM_FLATPAK, "--launch", "My Pack"]);
        assert_eq!(found[0].1.label, "neoforge 1.20.1");
        std::fs::remove_dir_all(data).unwrap();
    }

    #[test]
    fn the_same_name_twice_stays_two_rows() {
        let mut names = HashMap::new();
        assert_eq!(unique(&mut names, "Minecraft 26.3".into(), "Prism", "26.3"), "Minecraft 26.3");
        assert_eq!(
            unique(&mut names, "Minecraft 26.3".into(), "Prism Flatpak", "26.3"),
            "Minecraft 26.3 (Prism Flatpak)"
        );
        assert_eq!(unique(&mut names, "Minecraft 26.3".into(), "Prism", "26.3(1)"), "Minecraft 26.3 (26.3(1))");
        assert_eq!(
            unique(&mut names, "Minecraft 26.3".into(), "Prism Flatpak", "26.3(1)"),
            "Minecraft 26.3 (Prism Flatpak 26.3(1))"
        );
    }

    #[test]
    fn the_appimage_stands_in_for_the_package() {
        let dir = temp("appimage");
        assert_eq!(appimage(std::slice::from_ref(&dir)), None);
        write(dir.join("Apps/PrismLauncher-Linux-x86_64.AppImage"), "");
        let places = places(std::slice::from_ref(&dir));
        assert_eq!(appimage(&places), Some(dir.join("Apps/PrismLauncher-Linux-x86_64.AppImage")));
        write(dir.join(".hidden/MultiMC/multimc.cfg"), "");
        assert!(!places.contains(&dir.join(".hidden")));
        std::fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn portable_launchers_need_their_settings_and_program() {
        let dir = temp("portable");
        let multimc = dir.join("MultiMC");
        write(multimc.join("multimc.cfg"), "InstanceDir=instances\n");
        assert_eq!(portable(&multimc), None, "no program");
        write(multimc.join("MultiMC"), "");
        let root = portable(&multimc).unwrap();
        assert_eq!(
            (root.title.as_str(), root.program, root.settings),
            ("MultiMC", multimc.join("MultiMC"), "multimc.cfg")
        );
        let prism = dir.join("PrismLauncher-portable");
        write(prism.join("prismlauncher.cfg"), "");
        write(prism.join("bin/prismlauncher"), "");
        assert_eq!(portable(&prism).unwrap().program, prism.join("bin/prismlauncher"));
        assert_eq!(portable(&dir), None);

        write(multimc.join("instances/Pack/instance.cfg"), "name=Pack\n");
        let roots = roots(&places(std::slice::from_ref(&dir)));
        assert!(roots.iter().any(|root| root.data == multimc), "{roots:?}");
        std::fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn launchers_that_are_gone_are_skipped() {
        let dir = temp("gone");
        let program = dir.join("bin/prismlauncher");
        assert!(!runnable(&root(&dir, "Prism", program.to_str().unwrap(), &[])));
        write(program.clone(), "");
        assert!(runnable(&root(&dir, "Prism", program.to_str().unwrap(), &[])));
        assert!(!runnable(&root(&dir, "Prism", "surely-not-a-program-hanami", &[])));
        assert!(runnable(&root(&dir, "Prism", "sh", &[])));
        assert!(!runnable(&root(&dir, "Prism Flatpak", "flatpak", &["run", "org.example.NotInstalled"])));
        std::fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn odd_cfg_values_are_read_as_written() {
        assert_eq!(ini_value("[General]\nname=a=b\n", "name").as_deref(), Some("a=b"));
        assert_eq!(ini_value("name=\" spaced \"\n", "name").as_deref(), Some(" spaced "));
        assert_eq!(ini_value("name=back\\\\slash\n", "name").as_deref(), Some("back\\slash"));
        assert_eq!(ini_value("names=x\n", "name"), None);
        assert_eq!(icon_file(Path::new("/"), "../etc/passwd"), None);
        assert_eq!(ini_value("name=Caf\\xe9 \\x4e2d\\x6587\n", "name").as_deref(), Some("Café 中文"));
        assert_eq!(ini_value("name=a\\xzz\n", "name").as_deref(), Some("axzz"));
        assert_eq!(super::pack("{}"), None);
        assert_eq!(super::pack("not json"), None);
    }
}
