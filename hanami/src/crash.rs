//! Crash reports the user sends themselves. When Hanami hits a bug (a Rust
//! panic), what happened goes into a small file; the next start says so in
//! the panel, and "Report a problem" in the tray menu opens a new GitHub
//! issue with it filled in. Nothing leaves the computer unless the user
//! submits that issue. Crashes outside Rust (a driver taking the process
//! down) leave no file.

use std::fs;
use std::io::Write;
use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};

const NEW_ISSUE: &str = "https://github.com/sjdsjadjajdjsa/hanami/issues/new";
/// GitHub refuses links much longer than about 8 KB; the crash is cut to fit.
const MAX_LINK: usize = 7500;
/// Later bugs in one run are usually caused by the first; past this many
/// bytes, they aren't written down.
const MAX_FILE: u64 = 16 * 1024;

fn dir() -> Option<PathBuf> {
    dirs::data_local_dir().map(|dir| dir.join("hanami"))
}

/// Written by the panic hook, not yet seen by a start.
fn fresh() -> Option<PathBuf> {
    dir().map(|dir| dir.join("crash.txt"))
}

/// Seen by a start, kept until a report is opened.
fn kept() -> Option<PathBuf> {
    dir().map(|dir| dir.join("last-crash.txt"))
}

/// Adds every panic to the crash file, then reports it as Rust would.
pub fn install() {
    install_at(fresh());
}

fn install_at(file: Option<PathBuf>) {
    let default = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |info| {
        let message = info
            .payload()
            .downcast_ref::<&str>()
            .map(|s| s.to_string())
            .or_else(|| info.payload().downcast_ref::<String>().cloned())
            .unwrap_or_else(|| "(no message)".into());
        let place = info.location().map(|l| format!("{}:{}", l.file(), l.line())).unwrap_or_default();
        let thread = std::thread::current().name().unwrap_or("unnamed").to_owned();
        let when = SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0);
        let text = format!("{message}\nat {place}, thread {thread}, unix time {when}\n\n");
        if let Some(path) = &file {
            let _ = fs::create_dir_all(path.parent().unwrap_or(path));
            let full = fs::metadata(path).is_ok_and(|m| m.len() > MAX_FILE);
            if !full && let Ok(mut out) = fs::OpenOptions::new().create(true).append(true).open(path) {
                let _ = out.write_all(text.as_bytes());
            }
        }
        default(info);
    }));
}

/// True once after a bug: the start that should say so. What went wrong
/// stays for "Report a problem" until a report is opened.
pub fn crashed_last_time() -> bool {
    let (Some(fresh), Some(kept)) = (fresh(), kept()) else { return false };
    let Ok(text) = fs::read_to_string(&fresh) else { return false };
    // Added to anything not yet reported, oldest first.
    let mut all = fs::read_to_string(&kept).unwrap_or_default();
    all.push_str(&text);
    fs::write(&kept, all).is_ok() && fs::remove_file(&fresh).is_ok()
}

/// The link to a new issue, with this computer's details and any bug not
/// yet reported, from an earlier run or this one.
pub fn report_link() -> String {
    let crash: String = [kept(), fresh()].into_iter().flatten().filter_map(|p| fs::read_to_string(p).ok()).collect();
    let crash = (!crash.trim().is_empty()).then(|| without_home(&crash));
    let title = if crash.is_some() { "Hanami hit a bug" } else { "" };
    link(title, crash.as_deref())
}

/// A report was opened in the browser: what it carried isn't offered again.
pub fn reported() {
    for path in [kept(), fresh()].into_iter().flatten() {
        let _ = fs::remove_file(path);
    }
}

/// The issue link, with as much of `crash` as fits, from its start: the
/// first bug is usually the cause of the rest.
fn link(title: &str, crash: Option<&str>) -> String {
    let make = |crash: Option<&str>| format!("{NEW_ISSUE}?title={}&body={}", encode(title), encode(&body(crash)));
    let Some(crash) = crash else { return make(None) };
    let chars: Vec<char> = crash.chars().collect();
    let mut keep = chars.len();
    loop {
        let cut: String = chars[..keep].iter().collect();
        let made = make(Some(&cut));
        if made.len() <= MAX_LINK || keep == 0 {
            return made;
        }
        keep = keep * 4 / 5;
    }
}

fn body(crash: Option<&str>) -> String {
    let desktop = std::env::var("XDG_CURRENT_DESKTOP").unwrap_or_default();
    let session = std::env::var("XDG_SESSION_TYPE").unwrap_or_default();
    let mut text = format!(
        "What happened, and what did you do just before?\n\n\n\n---\nHanami {}, {} {}",
        env!("CARGO_PKG_VERSION"),
        std::env::consts::OS,
        std::env::consts::ARCH
    );
    if !desktop.is_empty() || !session.is_empty() {
        text.push_str(&format!(", {desktop} {session}"));
    }
    text.push('\n');
    if let Some(crash) = crash {
        text.push_str(&format!("\nWhat went wrong:\n```\n{}\n```\n", crash.trim_end()));
    }
    text
}

/// The user's folder as `~`, so the report doesn't carry their user name:
/// also as Rust's debug output writes it on Windows (`C:\\Users\\...`),
/// and in any case, as Windows paths are.
fn without_home(text: &str) -> String {
    match dirs::home_dir().and_then(|home| home.to_str().map(str::to_owned)) {
        Some(home) if home.len() > 1 => {
            let doubled = home.replace('\\', "\\\\");
            replace_ignoring_case(&replace_ignoring_case(text, &doubled), &home)
        }
        _ => text.to_owned(),
    }
}

fn replace_ignoring_case(text: &str, folder: &str) -> String {
    // ASCII case changes keep every byte where it was.
    let (lower, folder_lower) = (text.to_ascii_lowercase(), folder.to_ascii_lowercase());
    let mut out = String::with_capacity(text.len());
    let mut at = 0;
    while let Some(found) = lower[at..].find(&folder_lower) {
        out.push_str(&text[at..at + found]);
        out.push('~');
        at += found + folder.len();
    }
    out.push_str(&text[at..]);
    out
}

/// Percent-encoding for a link's query.
fn encode(text: &str) -> String {
    let mut out = String::with_capacity(text.len() * 3);
    for byte in text.bytes() {
        match byte {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => out.push(byte as char),
            _ => out.push_str(&format!("%{byte:02X}")),
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn links_are_encoded() {
        assert_eq!(encode("a b&c=d/é"), "a%20b%26c%3Dd%2F%C3%A9");
        assert_eq!(encode("Hanami-0.2_x.~"), "Hanami-0.2_x.~");
    }

    #[test]
    fn a_crash_fits_in_a_link() {
        // Spaces, slashes and accents grow threefold or more when encoded.
        let crash = "é / x ".repeat(5_000);
        let made = link("Hanami hit a bug", Some(&crash));
        assert!(made.len() <= MAX_LINK, "{}", made.len());
        assert!(made.contains("What%20went%20wrong"));
        assert!(made.contains(&encode(env!("CARGO_PKG_VERSION"))));
        assert!(link("", None).len() < MAX_LINK);
    }

    #[test]
    fn windows_home_folders_are_left_out_in_any_spelling() {
        let text = r#"couldn't read "C:\\Users\\Alice\\a.toml" or c:\users\alice\b.toml"#;
        assert_eq!(
            replace_ignoring_case(&replace_ignoring_case(text, r"C:\\Users\\Alice"), r"C:\Users\Alice"),
            r#"couldn't read "~\\a.toml" or ~\b.toml"#
        );
    }

    #[test]
    fn a_panic_is_written_down() {
        let file = std::env::temp_dir().join(format!("hanami-crash-test-{}.txt", std::process::id()));
        install_at(Some(file.clone()));
        // Two bugs in one run: both are kept, the first first.
        for n in 1..=2 {
            let _ = std::thread::Builder::new()
                .name("crashing".into())
                .spawn(move || panic!("the test's own panic {n}"))
                .unwrap()
                .join();
        }
        let _ = std::panic::take_hook();
        let text = fs::read_to_string(&file).unwrap();
        let _ = fs::remove_file(&file);
        assert!(text.starts_with("the test's own panic 1\nat "), "{text}");
        assert!(text.contains("the test's own panic 2\nat "), "{text}");
        assert!(text.contains("thread crashing"), "{text}");
    }

    #[test]
    fn the_home_folder_is_left_out() {
        if let Some(home) = dirs::home_dir().and_then(|h| h.to_str().map(str::to_owned))
            && home.len() > 1
        {
            assert_eq!(without_home(&format!("{home}/x.toml")), "~/x.toml");
        }
    }
}
