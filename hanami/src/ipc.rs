//! One Hanami at a time. The first copy listens on a local socket; later
//! copies, and `hanami --toggle` from a desktop shortcut, send it a word
//! and exit.

use std::io::{self, BufRead, BufReader, Write};

use interprocess::local_socket::prelude::*;
use interprocess::local_socket::{GenericNamespaced, ListenerOptions, Name, Stream};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Request {
    Open,
    Toggle,
    Nothing,
    Quit,
}

impl Request {
    fn word(self) -> &'static str {
        match self {
            Request::Open => "open",
            Request::Toggle => "toggle",
            Request::Nothing => "nothing",
            Request::Quit => "quit",
        }
    }

    fn from_word(word: &str) -> Option<Self> {
        [Request::Open, Request::Toggle, Request::Nothing, Request::Quit]
            .into_iter()
            .find(|request| request.word() == word)
    }
}

fn name() -> io::Result<Name<'static>> {
    let user = std::env::var("USER").or_else(|_| std::env::var("USERNAME")).unwrap_or_default();
    format!("hanami-{user}.sock").to_ns_name::<GenericNamespaced>()
}

/// Becomes the running copy, or hands `request` to the one already running.
/// Returns `None` when another copy took the request.
pub fn claim(request: Request, handle: impl Fn(Request) + Send + 'static) -> io::Result<Option<()>> {
    // Asking first works even where a second listener under the same name
    // isn't refused (Wine's named pipes).
    if let Ok(stream) = Stream::connect(name()?) {
        send(stream, request)?;
        return Ok(None);
    }
    match ListenerOptions::new().name(name()?).create_sync() {
        Ok(listener) => {
            std::thread::spawn(move || {
                for connection in listener.incoming().flatten() {
                    let mut line = String::new();
                    if BufReader::new(connection).read_line(&mut line).is_ok()
                        && let Some(request) = Request::from_word(line.trim())
                    {
                        handle(request);
                    }
                }
            });
            Ok(Some(()))
        }
        // Another copy started at the same moment.
        Err(error) if taken(&error) => {
            send(Stream::connect(name()?)?, request)?;
            Ok(None)
        }
        Err(error) => Err(error),
    }
}

/// Asks the running copy to quit and waits up to five seconds for it to be
/// gone, so its files can be replaced or removed right after. Returns
/// whether one was running.
pub fn quit_running() -> io::Result<bool> {
    let Ok(stream) = Stream::connect(name()?) else { return Ok(false) };
    send(stream, Request::Quit)?;
    for _ in 0..50 {
        std::thread::sleep(std::time::Duration::from_millis(100));
        if Stream::connect(name()?).is_err() {
            break;
        }
    }
    Ok(true)
}

fn send(mut stream: Stream, request: Request) -> io::Result<()> {
    allow_focus();
    stream.write_all(format!("{}\n", request.word()).as_bytes())
}

/// Another copy holds the name. Windows reports that as "access denied".
fn taken(error: &io::Error) -> bool {
    error.kind() == io::ErrorKind::AddrInUse || (cfg!(windows) && error.kind() == io::ErrorKind::PermissionDenied)
}

/// Windows lets only the app the user just started bring a window to the
/// front. That is this copy, so it hands the right to the running one.
#[cfg(windows)]
fn allow_focus() {
    use windows_sys::Win32::UI::WindowsAndMessaging::{ASFW_ANY, AllowSetForegroundWindow};
    // SAFETY: takes a process id, nothing else.
    unsafe {
        AllowSetForegroundWindow(ASFW_ANY);
    }
}

#[cfg(not(windows))]
fn allow_focus() {}

#[cfg(test)]
mod tests {
    use super::Request;

    #[test]
    fn words_round_trip() {
        for request in [Request::Open, Request::Toggle, Request::Nothing, Request::Quit] {
            assert_eq!(Request::from_word(request.word()), Some(request));
        }
        assert_eq!(Request::from_word("delete"), None);
    }
}
