//! Opening Hanami in the tray at login: a desktop entry in the autostart
//! folder on Linux, the Run key on Windows (the same one the installer's
//! tick box sets, so both agree).

use std::path::PathBuf;

/// The program to start: the AppImage itself when running from one.
pub fn program() -> Result<PathBuf, String> {
    let exe = std::env::current_exe().map_err(|e| format!("Couldn't find Hanami's own program: {e}"))?;
    // A program replaced while it runs (a package upgrade) reads as "… (deleted)".
    let exe = match exe.to_str().and_then(|path| path.strip_suffix(" (deleted)")) {
        Some(path) => PathBuf::from(path),
        None => exe,
    };
    // APPIMAGE is passed down to everything an AppImage starts, so it only
    // names Hanami when Hanami runs from inside that image.
    if let (Some(image), Some(inside)) = (std::env::var_os("APPIMAGE"), std::env::var_os("APPDIR"))
        && exe.starts_with(inside)
    {
        return Ok(PathBuf::from(image));
    }
    Ok(exe)
}

#[cfg(all(unix, not(target_vendor = "apple")))]
mod platform {
    use super::program;
    use std::path::PathBuf;

    fn entry() -> Option<PathBuf> {
        dirs::config_dir().map(|dir| dir.join("autostart").join("hanami.desktop"))
    }

    /// `Exec=` with the path quoted as the desktop entry spec wants.
    fn exec(path: &std::path::Path) -> String {
        let mut quoted = String::from("\"");
        for c in path.to_string_lossy().chars() {
            if matches!(c, '"' | '\\' | '$' | '`') {
                quoted.push('\\');
            }
            quoted.push(c);
        }
        quoted.push('"');
        format!("{quoted} --hidden")
    }

    /// On, unless the desktop's own startup settings switched the entry off.
    pub fn enabled() -> bool {
        entry().and_then(|path| std::fs::read_to_string(path).ok()).is_some_and(|text| !switched_off(&text))
    }

    /// Ubuntu's Startup Applications and XFCE turn an entry off in place.
    fn switched_off(text: &str) -> bool {
        text.lines().filter_map(|line| line.split_once('=')).any(|(key, value)| {
            matches!((key.trim(), value.trim()), ("Hidden", "true") | ("X-GNOME-Autostart-enabled", "false"))
        })
    }

    pub fn set(on: bool) -> Result<(), String> {
        let path = entry().ok_or("no settings folder")?;
        if !on {
            return match std::fs::remove_file(&path) {
                Err(e) if e.kind() != std::io::ErrorKind::NotFound => {
                    Err(format!("Couldn't remove {}: {e}", path.display()))
                }
                _ => Ok(()),
            };
        }
        let text = format!(
            "[Desktop Entry]\nType=Application\nName=Hanami\nComment=Game launcher in the tray\nExec={}\nIcon=hanami\nTerminal=false\nX-GNOME-Autostart-enabled=true\n",
            exec(&program()?)
        );
        if let Some(dir) = path.parent() {
            std::fs::create_dir_all(dir).map_err(|e| format!("Couldn't create {}: {e}", dir.display()))?;
        }
        crate::config::write_atomic(&path, &text)
    }

    #[cfg(test)]
    mod tests {
        use super::{exec, switched_off};
        use std::path::Path;

        #[test]
        fn entries_the_desktop_switched_off_are_off() {
            let on = "[Desktop Entry]\nExec=hanami --hidden\nX-GNOME-Autostart-enabled=true\n";
            assert!(!switched_off(on));
            assert!(switched_off(&on.replace("enabled=true", "enabled=false")));
            assert!(switched_off(&format!("{on}Hidden = true\n")));
            assert!(!switched_off(&format!("{on}Hidden=false\n")));
        }

        #[test]
        fn paths_are_quoted_for_the_desktop_entry() {
            assert_eq!(exec(Path::new("/opt/hanami")), "\"/opt/hanami\" --hidden");
            assert_eq!(exec(Path::new("/home/me/My Apps/hanami")), "\"/home/me/My Apps/hanami\" --hidden");
            assert_eq!(exec(Path::new("/a/$b\"c")), "\"/a/\\$b\\\"c\" --hidden");
        }
    }
}

#[cfg(windows)]
mod platform {
    use super::program;
    use winreg::RegKey;
    use winreg::enums::{HKEY_CURRENT_USER, KEY_READ, KEY_WRITE};

    const RUN: &str = r"Software\Microsoft\Windows\CurrentVersion\Run";
    /// Where Task Manager and Settings, Startup apps, switch a Run entry off
    /// without removing it: an odd first byte means off.
    const APPROVED: &str = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run";

    pub fn enabled() -> bool {
        let user = RegKey::predef(HKEY_CURRENT_USER);
        let set =
            user.open_subkey_with_flags(RUN, KEY_READ).and_then(|key| key.get_value::<String, _>("Hanami")).is_ok();
        let switched_off = user
            .open_subkey_with_flags(APPROVED, KEY_READ)
            .and_then(|key| key.get_raw_value("Hanami"))
            .is_ok_and(|value| value.bytes.first().is_some_and(|byte| byte % 2 == 1));
        set && !switched_off
    }

    pub fn set(on: bool) -> Result<(), String> {
        let user = RegKey::predef(HKEY_CURRENT_USER);
        let (key, _) = user
            .create_subkey_with_flags(RUN, KEY_READ | KEY_WRITE)
            .map_err(|e| format!("Couldn't open the Run key: {e}"))?;
        if on {
            let command = format!("\"{}\" --hidden", program()?.display());
            // Turning it on here also undoes an earlier switch-off in Task Manager.
            if let Ok(approved) = user.open_subkey_with_flags(APPROVED, KEY_WRITE) {
                let _ = approved.delete_value("Hanami");
            }
            key.set_value("Hanami", &command).map_err(|e| format!("Couldn't write the Run key: {e}"))
        } else {
            match key.delete_value("Hanami") {
                Err(e) if e.kind() != std::io::ErrorKind::NotFound => Err(format!("Couldn't clear the Run key: {e}")),
                _ => Ok(()),
            }
        }
    }

    #[cfg(test)]
    mod tests {
        use super::*;
        use winreg::RegValue;
        use winreg::enums::RegType::REG_BINARY;

        /// Runs against the real Run key of whoever runs the tests, and puts
        /// back what was there.
        #[test]
        fn the_run_key_is_set_and_cleared() {
            // A fresh account has no Run key yet.
            let (key, _) =
                RegKey::predef(HKEY_CURRENT_USER).create_subkey_with_flags(RUN, KEY_READ | KEY_WRITE).unwrap();
            let before: Option<String> = key.get_value("Hanami").ok();
            set(true).unwrap();
            assert!(enabled());
            let command: String = key.get_value("Hanami").unwrap();
            assert!(command.starts_with('"') && command.ends_with("\" --hidden"), "{command}");
            assert!(std::path::Path::new(&command[1..command.len() - 10]).exists(), "{command}");
            // Switched off in Task Manager: off, until turned on here again.
            let (approved, _) =
                RegKey::predef(HKEY_CURRENT_USER).create_subkey_with_flags(APPROVED, KEY_READ | KEY_WRITE).unwrap();
            let approved_before = approved.get_raw_value("Hanami").ok();
            let off = RegValue { bytes: vec![3, 0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8].into(), vtype: REG_BINARY };
            approved.set_raw_value("Hanami", &off).unwrap();
            assert!(!enabled());
            set(true).unwrap();
            assert!(enabled());
            assert!(approved.get_raw_value("Hanami").is_err());
            set(false).unwrap();
            assert!(!enabled());
            set(false).unwrap();
            if let Some(before) = before {
                key.set_value("Hanami", &before).unwrap();
            }
            if let Some(before) = approved_before {
                approved.set_raw_value("Hanami", &before).unwrap();
            }
        }
    }
}

#[cfg(target_vendor = "apple")]
mod platform {
    pub fn enabled() -> bool {
        false
    }

    pub fn set(_on: bool) -> Result<(), String> {
        Err("Opening at login isn't set up for macOS yet.".into())
    }
}

pub use platform::{enabled, set};

/// Points a login entry at the program running now: an AppImage or a
/// portable folder may have moved since the entry was made.
pub fn refresh() -> Result<(), String> {
    if enabled() { set(true) } else { Ok(()) }
}
