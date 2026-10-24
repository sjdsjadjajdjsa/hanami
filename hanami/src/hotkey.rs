//! The hotkey on Wayland, where no app can grab a key itself: KDE Plasma and
//! GNOME let a program ask for a shortcut in the desktop's own settings, the
//! same place the user would add one by hand, so Hanami asks for its own.
//! On X11, Hanami grabs the key itself and waits for the X server to say it
//! was pressed.

/// The keys of a hotkey like "Ctrl+Alt+H", pulled apart.
#[derive(Debug, PartialEq)]
struct Keys {
    text: String,
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
    let mut keys =
        Keys { text: text.trim().into(), ctrl: false, alt: false, shift: false, meta: false, key: Key::Space };
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

    /// Asks the desktop to run `hanami --toggle` on `text`. Ok says what was
    /// done, for the log; Err carries a reason the panel can show.
    pub fn bind(text: &str) -> Result<String, String> {
        let keys = parse(text)?;
        let desktop = std::env::var("XDG_CURRENT_DESKTOP").unwrap_or_default().to_ascii_uppercase();
        let command = crate::autostart::program()?;
        let command = command.to_string_lossy();
        if desktop.split(':').any(|d| d == "KDE") {
            kde(&keys, &command).map(|done| done.message("KDE"))
        } else if desktop.split(':').any(|d| d == "GNOME" || d == "UBUNTU") {
            gnome(&keys, &command).map(|done| done.message("GNOME"))
        } else {
            Err("No built-in hotkey on this Wayland desktop: bind hanami --toggle to a key".into())
        }
    }

    enum Done {
        Added,
        Kept,
    }

    impl Done {
        fn message(self, desktop: &str) -> String {
            match self {
                Done::Added => format!("hotkey added to {desktop}'s shortcuts"),
                Done::Kept => format!("hotkey is whatever {desktop}'s shortcuts say"),
            }
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
    /// kglobalshortcutsrc for the next login. The entry lives in the
    /// service's own folder, which it reads directly: the app menu's folder
    /// goes through a cache that lags behind a new file.
    fn kde(keys: &Keys, command: &str) -> Result<Done, String> {
        let data = dirs::data_dir().ok_or("no data folder")?;
        let dir = data.join("kglobalaccel");
        let path = dir.join(KDE_ENTRY);
        let text = format!(
            "[Desktop Entry]\nType=Application\nName=Hanami\nExec={} --toggle\nIcon=hanami\nNoDisplay=true\nX-KDE-GlobalAccel-CommandShortcut=true\n",
            quote(command)
        );
        if std::fs::read_to_string(&path).ok().as_deref() != Some(text.as_str()) {
            std::fs::create_dir_all(&dir).map_err(|e| format!("Couldn't create {}: {e}", dir.display()))?;
            crate::config::write_atomic(&path, &text)?;
        }
        // 0.2.6 put the entry in the app menu's folder, where it took
        // precedence; its path could go stale.
        let _ = std::fs::remove_file(data.join("applications").join(KDE_ENTRY));
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
        // Register the entry, as System Settings does. That also loads a key
        // the user gave it there; that key stays theirs.
        call("doRegister", &[&format!("['{KDE_ENTRY}','','Hanami','']")])?;
        call("unregister", &[KDE_ENTRY, ""])?;
        // An empty reply looks like `(@a(ai) [],)`; a key like `([([201326664, 0, 0, 0],)],)`.
        let current = call("shortcutKeys", &[&id])?;
        if current.contains("[(") {
            return Ok(Done::Kept);
        }
        let holder = call("globalShortcutsByKey", &[&format!("([{code},0,0,0],)"), "(0,)"])?;
        if let Some(other) = holder.split('\'').nth(3).filter(|_| !holder.contains(KDE_ENTRY)) {
            return Err(format!("{} is {other}'s key in KDE. Pick another hotkey in settings.", keys.text));
        }
        // 2 = make it live now, 4 = this key, not one from the settings file.
        let reply = call("setShortcutKeys", &[&id, &format!("[([{code},0,0,0],)]"), "6"])?;
        if reply.contains(&format!("[{code}, 0, 0, 0]")) {
            Ok(Done::Added)
        } else {
            Err("KDE wouldn't give Hanami this key. Pick another hotkey in settings.".into())
        }
    }

    /// GNOME keeps custom shortcuts in gsettings, as a list of paths each
    /// with a name, command and key.
    fn gnome(keys: &Keys, command: &str) -> Result<Done, String> {
        let list = run("gsettings", &["get", GNOME_SCHEMA, "custom-keybindings"])?;
        let mut paths: Vec<String> = list
            .trim()
            .trim_start_matches("@as ")
            .trim_matches(['[', ']'])
            .split(',')
            .map(|p| p.trim().trim_matches('\'').to_string())
            .filter(|p| !p.is_empty())
            .collect();
        let schema = |path: &str| format!("{GNOME_SCHEMA}.custom-keybinding:{path}");
        let command = literal(&format!("{} --toggle", quote(command)));
        if paths.iter().any(|p| p == GNOME_PATH) {
            // Already there: the key is the user's to change; only the
            // program's path is kept fresh.
            if run("gsettings", &["get", &schema(GNOME_PATH), "command"])?.trim() != command {
                run("gsettings", &["set", &schema(GNOME_PATH), "command", &command])?;
            }
            return Ok(Done::Kept);
        }
        let binding = literal(&keys.gtk());
        for path in &paths {
            if run("gsettings", &["get", &schema(path), "binding"]).is_ok_and(|taken| taken.trim() == binding) {
                let name = run("gsettings", &["get", &schema(path), "name"]).unwrap_or_default();
                let name = name.trim().trim_matches('\'').to_owned();
                return Err(format!("{} is {name}'s key in GNOME. Pick another hotkey in settings.", keys.text));
            }
        }
        paths.push(GNOME_PATH.into());
        let value = format!("[{}]", paths.iter().map(|p| format!("'{p}'")).collect::<Vec<_>>().join(", "));
        run("gsettings", &["set", &schema(GNOME_PATH), "name", &literal("Hanami")])?;
        run("gsettings", &["set", &schema(GNOME_PATH), "command", &command])?;
        run("gsettings", &["set", &schema(GNOME_PATH), "binding", &binding])?;
        run("gsettings", &["set", GNOME_SCHEMA, "custom-keybindings", &value])?;
        Ok(Done::Added)
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

/// global-hotkey looks for a press every 50 ms for as long as Hanami runs;
/// this sleeps until the X server has one, so a hidden Hanami does no work.
#[cfg(target_os = "linux")]
mod x11 {
    use x11rb::connection::Connection;
    use x11rb::protocol::Event;
    use x11rb::protocol::xkb::{self, ConnectionExt as _};
    use x11rb::protocol::xproto::{ConnectionExt as _, GrabMode, KeyButMask, Keycode, ModMask};
    use x11rb::rust_connection::RustConnection;

    use super::{Key, Keys, parse};

    /// Calls `pressed` on another thread each time the hotkey goes down.
    /// Ok(false): a key only global-hotkey knows, for it to grab instead.
    pub fn grab(text: &str, pressed: fn()) -> Result<bool, String> {
        let Ok(keys) = parse(text) else { return Ok(false) };
        let none = || "No built-in hotkey here: bind hanami --toggle in your desktop's shortcut settings.".to_string();
        let (conn, screen) = RustConnection::connect(None).map_err(|_| none())?;
        let root = conn.setup().roots[screen].root;
        let Some(keycode) = keycode(&conn, keysym(&keys)) else { return Ok(false) };
        // Holding the keys then repeats presses only, not release and press.
        if let Ok(asked) = conn.xkb_use_extension(1, 0) {
            let _ = asked.reply();
        }
        let repeat = xkb::PerClientFlag::DETECTABLE_AUTO_REPEAT;
        if let Ok(asked) = conn.xkb_per_client_flags(
            xkb::ID::USE_CORE_KBD.into(),
            repeat,
            repeat,
            Default::default(),
            Default::default(),
            Default::default(),
        ) {
            let _ = asked.reply();
        }
        let mods = mods(&keys);
        // Caps Lock and Num Lock arrive as modifiers too.
        for locks in [ModMask::default(), ModMask::LOCK, ModMask::M2, ModMask::LOCK | ModMask::M2] {
            conn.grab_key(false, root, mods | locks, keycode, GrabMode::ASYNC, GrabMode::ASYNC)
                .map_err(|_| none())?
                .check()
                .map_err(|_| format!("{text} is taken by another app. Pick another hotkey in settings."))?;
        }
        std::thread::spawn(move || {
            let counted = KeyButMask::CONTROL | KeyButMask::SHIFT | KeyButMask::MOD1 | KeyButMask::MOD4;
            let wanted = KeyButMask::from(u16::from(mods));
            let mut down = false;
            while let Ok(event) = conn.wait_for_event() {
                match event {
                    Event::KeyPress(press) if press.detail == keycode && (press.state & counted) == wanted => {
                        // Holding the keys repeats the press; only the first one counts.
                        if !down {
                            down = true;
                            pressed();
                        }
                    }
                    Event::KeyRelease(release) if release.detail == keycode => down = false,
                    _ => {}
                }
            }
        });
        Ok(true)
    }

    pub(super) fn keysym(keys: &Keys) -> u32 {
        match keys.key {
            Key::Letter(c) | Key::Digit(c) => c as u32,
            Key::Function(n) => 0xffbe + u32::from(n) - 1,
            Key::Space => 0x20,
        }
    }

    pub(super) fn mods(keys: &Keys) -> ModMask {
        let mut mods = ModMask::default();
        for (on, mask) in [
            (keys.ctrl, ModMask::CONTROL),
            (keys.alt, ModMask::M1),
            (keys.shift, ModMask::SHIFT),
            (keys.meta, ModMask::M4),
        ] {
            if on {
                mods |= mask;
            }
        }
        mods
    }

    /// The key on this keyboard that types `keysym`.
    fn keycode(conn: &RustConnection, keysym: u32) -> Option<Keycode> {
        let (min, max) = (conn.setup().min_keycode, conn.setup().max_keycode);
        let map = conn.get_keyboard_mapping(min, max - min + 1).ok()?.reply().ok()?;
        let per = usize::from(map.keysyms_per_keycode);
        if per == 0 {
            return None;
        }
        let index = map.keysyms.chunks(per).position(|keysyms| keysyms.contains(&keysym))?;
        min.checked_add(u8::try_from(index).ok()?)
    }
}

#[cfg(target_os = "linux")]
pub use x11::grab;

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

    #[cfg(target_os = "linux")]
    #[test]
    fn hotkeys_become_x11_keysyms_and_modifiers() {
        use x11rb::protocol::xproto::ModMask;

        let keys = parse("Ctrl+Alt+H").unwrap();
        assert_eq!(super::x11::keysym(&keys), 0x68);
        assert_eq!(super::x11::mods(&keys), ModMask::CONTROL | ModMask::M1);
        let keys = parse("Super+Shift+F12").unwrap();
        assert_eq!(super::x11::keysym(&keys), 0xffc9);
        assert_eq!(super::x11::mods(&keys), ModMask::SHIFT | ModMask::M4);
        assert_eq!(super::x11::keysym(&parse("Ctrl+Alt+1").unwrap()), 0x31);
        assert_eq!(super::x11::keysym(&parse("Ctrl+Space").unwrap()), 0x20);
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
