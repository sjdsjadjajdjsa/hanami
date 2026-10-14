//! Opening Hanami in the tray at login: a desktop entry in the autostart
//! folder on Linux, the Run key on Windows (the same one the installer's
//! tick box sets, so both agree).

use std::path::PathBuf;

/// The program to start: the AppImage itself when running from one.
fn program() -> Result<PathBuf, String> {
    if let Some(image) = std::env::var_os("APPIMAGE") {
        return Ok(PathBuf::from(image));
    }
    std::env::current_exe().map_err(|e| format!("Couldn't find Hanami's own program: {e}"))
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

    pub fn enabled() -> bool {
        entry().is_some_and(|path| path.exists())
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
        use super::exec;
        use std::path::Path;

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
    use winreg::enums::{HKEY_CURRENT_USER, KEY_READ, KEY_WRITE};
    use winreg::RegKey;

    const RUN: &str = r"Software\Microsoft\Windows\CurrentVersion\Run";

    pub fn enabled() -> bool {
        RegKey::predef(HKEY_CURRENT_USER)
            .open_subkey_with_flags(RUN, KEY_READ)
            .and_then(|key| key.get_value::<String, _>("Hanami"))
            .is_ok()
    }

    pub fn set(on: bool) -> Result<(), String> {
        let (key, _) = RegKey::predef(HKEY_CURRENT_USER)
            .create_subkey_with_flags(RUN, KEY_READ | KEY_WRITE)
            .map_err(|e| format!("Couldn't open the Run key: {e}"))?;
        if on {
            let command = format!("\"{}\" --hidden", program()?.display());
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

        /// Runs against the real Run key of whoever runs the tests, and puts
        /// back what was there.
        #[test]
        fn the_run_key_is_set_and_cleared() {
            // A fresh account has no Run key yet.
            let (key, _) = RegKey::predef(HKEY_CURRENT_USER).create_subkey_with_flags(RUN, KEY_READ | KEY_WRITE).unwrap();
            let before: Option<String> = key.get_value("Hanami").ok();
            set(true).unwrap();
            assert!(enabled());
            let command: String = key.get_value("Hanami").unwrap();
            assert!(command.starts_with('"') && command.ends_with("\" --hidden"), "{command}");
            assert!(std::path::Path::new(&command[1..command.len() - 10]).exists(), "{command}");
            set(false).unwrap();
            assert!(!enabled());
            set(false).unwrap();
            if let Some(before) = before {
                key.set_value("Hanami", &before).unwrap();
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
