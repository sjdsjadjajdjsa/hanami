//! The hotkey on Wayland, where no app can grab a key itself: KDE Plasma and
//! GNOME let a program ask for a shortcut in the desktop's own settings, the
//! same place the user would add one by hand, so Hanami asks for its own.

/// The keys of a hotkey like "Ctrl+Alt+H", pulled apart.
#[derive(Debug, PartialEq)]
struct Keys {
    ctrl: bool,
    alt: bool,
    shift: bool,
    meta: bool,
    key: Key,
}

#[derive(Debug, PartialEq)]
enum Key {
    Letter(char),
    Digit(char),
    Function(u8),
    Space,
}

fn parse(text: &str) -> Result<Keys, String> {
    let mut keys = Keys { ctrl: false, alt: false, shift: false, meta: false, key: Key::Space };
    let mut key = None;
    for part in text.split('+').map(str::trim).filter(|p| !p.is_empty()) {
        match part.to_ascii_lowercase().as_str() {
            "ctrl" | "control" => keys.ctrl = true,
            "alt" | "option" => keys.alt = true,
            "shift" => keys.shift = true,
            "super" | "meta" | "win" | "cmd" | "command" => keys.meta = true,
            "space" => key = Some(Key::Space),
            name => {
                let mut chars = name.chars();
                key = Some(match (chars.next(), chars.next()) {
                    (Some(c), None) if c.is_ascii_lowercase() => Key::Letter(c),
                    (Some(c), None) if c.is_ascii_digit() => Key::Digit(c),
                    (Some('f'), Some(_)) => match name[1..].parse::<u8>() {
                        Ok(n @ 1..=24) => Key::Function(n),
                        _ => return Err(format!("{part} isn't a key the desktop can bind.")),
                    },
                    _ => return Err(format!("{part} isn't a key the desktop can bind.")),
                });
            }
        }
    }
    keys.key = key.ok_or_else(|| format!("\"{text}\" names no key."))?;
    if !(keys.ctrl || keys.alt || keys.meta) {
        return Err(format!("\"{text}\" needs Ctrl, Alt or Super in it."));
    }
    Ok(keys)
}

impl Keys {
    /// Qt's number for the key, as KDE's shortcut service wants it.
    fn qt(&self) -> u32 {
        let key = match self.key {
            Key::Letter(c) => c.to_ascii_uppercase() as u32,
            Key::Digit(c) => c as u32,
            Key::Function(n) => 0x0100_0030 + n as u32 - 1,
            Key::Space => 0x20,
        };
        key | if self.shift { 0x0200_0000 } else { 0 }
            | if self.ctrl { 0x0400_0000 } else { 0 }
            | if self.alt { 0x0800_0000 } else { 0 }
            | if self.meta { 0x1000_0000 } else { 0 }
    }

    /// GTK's spelling, like `<Control><Alt>h`.
    fn gtk(&self) -> String {
        let mut text = String::new();
        for (on, name) in
            [(self.shift, "<Shift>"), (self.ctrl, "<Control>"), (self.alt, "<Alt>"), (self.meta, "<Super>")]
        {
            if on {
                text.push_str(name);
            }
        }
        match self.key {
            Key::Letter(c) | Key::Digit(c) => text.push(c),
            Key::Function(n) => text.push_str(&format!("F{n}")),
            Key::Space => text.push_str("space"),
        }
        text
    }
}

mod platform {
    use std::process::Command;

    use super::{Keys, parse};

    const KDE_ENTRY: &str = "hanami-toggle.desktop";
    const GNOME_PATH: &str = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/hanami/";
    const GNOME_SCHEMA: &str = "org.gnome.settings-daemon.plugins.media-keys";

    /// Asks the desktop to run `hanami --toggle` on `text`. Ok(desktop name)
    /// when it took; Err with a reason the panel can show otherwise.
    pub fn bind(text: &str) -> Result<&'static str, String> {
        let keys = parse(text)?;
        let desktop = std::env::var("XDG_CURRENT_DESKTOP").unwrap_or_default().to_ascii_uppercase();
        let command = crate::autostart::program()?;
        let command = command.to_string_lossy();
        if desktop.split(':').any(|d| d == "KDE") {
            kde(&keys, &command).map(|()| "KDE")
        } else if desktop.split(':').any(|d| d == "GNOME" || d == "UBUNTU") {
            gnome(&keys, &command).map(|()| "GNOME")
        } else {
            Err("No built-in hotkey on this Wayland desktop: bind hanami --toggle to a key".into())
        }
    }

    fn run(program: &str, args: &[&str]) -> Result<String, String> {
        let output = Command::new(program).args(args).output().map_err(|e| format!("Couldn't run {program}: {e}"))?;
        if output.status.success() {
            Ok(String::from_utf8_lossy(&output.stdout).into_owned())
        } else {
            Err(format!("{program} failed: {}", String::from_utf8_lossy(&output.stderr).trim()))
        }
    }

    /// KDE keeps command shortcuts as desktop entries; the shortcut service
    /// is asked the way System Settings asks it, and remembers the key in
    /// kglobalshortcutsrc for the next login.
    fn kde(keys: &Keys, command: &str) -> Result<(), String> {
        let dir = dirs::data_dir().ok_or("no data folder")?.join("applications");
        let path = dir.join(KDE_ENTRY);
        let text = format!(
            "[Desktop Entry]\nType=Application\nName=Hanami\nExec={} --toggle\nIcon=hanami\nNoDisplay=true\nX-KDE-GlobalAccel-CommandShortcut=true\n",
            quote(command)
        );
        if std::fs::read_to_string(&path).ok().as_deref() != Some(text.as_str()) {
            std::fs::create_dir_all(&dir).map_err(|e| format!("Couldn't create {}: {e}", dir.display()))?;
            crate::config::write_atomic(&path, &text)?;
            // The shortcut service finds entries through KDE's cache.
            let _ = Command::new("kbuildsycoca6").output();
        }
        let call = |method: &str, args: &[&str]| {
            let mut all = vec![
                "call",
                "--session",
                "--dest",
                "org.kde.kglobalaccel",
                "--object-path",
                "/kglobalaccel",
                "--method",
            ];
            let method = format!("org.kde.KGlobalAccel.{method}");
            all.push(&method);
            all.extend_from_slice(args);
            run("gdbus", &all)
        };
        let id = format!("['{KDE_ENTRY}','_launch','Hanami','Hanami']");
        let code = keys.qt();
        // Register the entry (System Settings does the same), then set the key:
        // 2 = make it live now, 4 = don't take an older key from the settings.
        call("doRegister", &[&format!("['{KDE_ENTRY}','','Hanami','']")])?;
        call("unregister", &[KDE_ENTRY, ""])?;
        let reply = call("setShortcutKeys", &[&id, &format!("[([{code},0,0,0],)]"), "6"])?;
        if reply.contains(&format!("[{code}, 0, 0, 0]")) {
            Ok(())
        } else {
            Err("KDE wouldn't give Hanami this key; another shortcut may have it. Pick another hotkey in settings."
                .into())
        }
    }

    /// GNOME keeps custom shortcuts in gsettings, as a list of paths each
    /// with a name, command and key.
    fn gnome(keys: &Keys, command: &str) -> Result<(), String> {
        let list = run("gsettings", &["get", GNOME_SCHEMA, "custom-keybindings"])?;
        if !list.contains(GNOME_PATH) {
            let mut paths: Vec<String> = list
                .trim()
                .trim_start_matches("@as ")
                .trim_matches(['[', ']'])
                .split(',')
                .map(|p| p.trim().trim_matches('\'').to_string())
                .filter(|p| !p.is_empty())
                .collect();
            paths.push(GNOME_PATH.into());
            let value = format!("[{}]", paths.iter().map(|p| format!("'{p}'")).collect::<Vec<_>>().join(", "));
            run("gsettings", &["set", GNOME_SCHEMA, "custom-keybindings", &value])?;
        }
        let schema = format!("{GNOME_SCHEMA}.custom-keybinding:{GNOME_PATH}");
        run("gsettings", &["set", &schema, "name", &literal("Hanami")])?;
        run("gsettings", &["set", &schema, "command", &literal(&format!("{} --toggle", quote(command)))])?;
        run("gsettings", &["set", &schema, "binding", &literal(&keys.gtk())])?;
        Ok(())
    }

    /// A string as gsettings reads values: in single quotes.
    pub(super) fn literal(text: &str) -> String {
        format!("'{}'", text.replace('\\', "\\\\").replace('\'', "\\'"))
    }

    /// A path quoted for a desktop entry's `Exec` and for a shell.
    fn quote(path: &str) -> String {
        let mut quoted = String::from("\"");
        for c in path.chars() {
            if matches!(c, '"' | '\\' | '$' | '`') {
                quoted.push('\\');
            }
            quoted.push(c);
        }
        quoted.push('"');
        quoted
    }
}

pub use platform::bind;

#[cfg(test)]
mod tests {
    use super::{Key, parse};

    #[test]
    fn hotkeys_become_qt_codes_and_gtk_names() {
        let keys = parse("Ctrl+Alt+H").unwrap();
        assert_eq!(keys.key, Key::Letter('h'));
        assert_eq!(keys.qt(), 0x0C00_0048);
        assert_eq!(keys.gtk(), "<Control><Alt>h");
        let keys = parse("Super+F5").unwrap();
        assert_eq!(keys.qt(), 0x1100_0034);
        assert_eq!(keys.gtk(), "<Super>F5");
        assert_eq!(parse("Shift+Ctrl+Space").unwrap().gtk(), "<Shift><Control>space");
        assert_eq!(parse("Ctrl+Alt+1").unwrap().qt(), 0x0C00_0031);
    }

    #[test]
    fn gsettings_values_are_quoted() {
        assert_eq!(super::platform::literal("Hanami"), "'Hanami'");
        assert_eq!(super::platform::literal("\"/a b/x\" --toggle"), "'\"/a b/x\" --toggle'");
        assert_eq!(super::platform::literal("it's"), "'it\\'s'");
    }

    #[test]
    fn keys_the_desktop_cannot_bind_are_refused() {
        assert!(parse("H").is_err());
        assert!(parse("Ctrl+Alt").is_err());
        assert!(parse("Ctrl+Alt+Comma").is_err());
        assert!(parse("Ctrl+F99").is_err());
    }
}
