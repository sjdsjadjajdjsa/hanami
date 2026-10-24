//! Crash reports the user sends themselves. When Hanami hits a bug (a Rust
//! panic), what happened goes into a small file; the next start says so in
//! the panel, and "Report a problem" in the tray menu opens a new GitHub
//! issue with it filled in. Nothing leaves the computer unless the user
//! submits that issue. Crashes outside Rust (a driver taking the process
//! down) leave no file.

use std::fs;
use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};

const NEW_ISSUE: &str = "https://github.com/sjdsjadjajdjsa/hanami/issues/new";
/// GitHub refuses very long links; the crash is cut to fit.
const MAX_BODY: usize = 6000;

fn dir() -> Option<PathBuf> {
    dirs::data_local_dir().map(|dir| dir.join("hanami"))
}

/// Written by the panic hook, not yet seen by a start.
fn fresh() -> Option<PathBuf> {
    dir().map(|dir| dir.join("crash.txt"))
}

/// Seen by a start, kept until it is reported.
fn kept() -> Option<PathBuf> {
    dir().map(|dir| dir.join("last-crash.txt"))
}

/// Writes every panic to the crash file, then reports it as Rust would.
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
        let text = format!("{message}\nat {place}, thread {thread}, unix time {when}\n");
        if let Some(path) = &file {
            let _ = fs::create_dir_all(path.parent().unwrap_or(path));
            let _ = fs::write(path, &text);
        }
        default(info);
    }));
}

/// True once after a crash: the start that should say so. The crash stays
/// for "Report a problem" until it is reported.
pub fn crashed_last_time() -> bool {
    let (Some(fresh), Some(kept)) = (fresh(), kept()) else { return false };
    fresh.exists() && fs::rename(fresh, kept).is_ok()
}

/// The link to a new issue, with this computer's details and the last
/// crash, if any.
pub fn report_link() -> String {
    let crash = kept().and_then(|path| fs::read_to_string(path).ok());
    let title = if crash.is_some() { "Hanami crashed" } else { "" };
    format!("{NEW_ISSUE}?title={}&body={}", encode(title), encode(&body(crash.as_deref())))
}

/// The issue has been opened in the browser: the crash is not offered again.
pub fn reported() {
    if let Some(path) = kept() {
        let _ = fs::remove_file(path);
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
        let crash = without_home(crash);
        let room = MAX_BODY.saturating_sub(text.len() + 32);
        let cut: String = crash.chars().take(room).collect();
        text.push_str(&format!("\nThe crash:\n```\n{}\n```\n", cut.trim_end()));
    }
    text
}

/// The user's folder as `~`, so the report doesn't carry their user name.
fn without_home(text: &str) -> String {
    match dirs::home_dir().and_then(|home| home.to_str().map(str::to_owned)) {
        Some(home) if home.len() > 1 => text.replace(&home, "~"),
        _ => text.to_owned(),
    }
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
        let crash = "x".repeat(50_000);
        let text = body(Some(&crash));
        assert!(text.len() <= MAX_BODY);
        assert!(text.contains("The crash:"));
        assert!(text.contains(env!("CARGO_PKG_VERSION")));
    }

    #[test]
    fn a_panic_is_written_down() {
        let file = std::env::temp_dir().join(format!("hanami-crash-test-{}.txt", std::process::id()));
        install_at(Some(file.clone()));
        let _ = std::thread::Builder::new()
            .name("crashing".into())
            .spawn(|| panic!("the test's own panic"))
            .unwrap()
            .join();
        let _ = std::panic::take_hook();
        let text = fs::read_to_string(&file).unwrap();
        let _ = fs::remove_file(&file);
        assert!(text.starts_with("the test's own panic\nat "), "{text}");
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
