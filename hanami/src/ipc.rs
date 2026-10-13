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
}

impl Request {
    fn word(self) -> &'static str {
        match self {
            Request::Open => "open",
            Request::Toggle => "toggle",
            Request::Nothing => "nothing",
        }
    }

    fn from_word(word: &str) -> Option<Self> {
        [Request::Open, Request::Toggle, Request::Nothing].into_iter().find(|request| request.word() == word)
    }
}

fn name() -> io::Result<Name<'static>> {
    let user = std::env::var("USER").or_else(|_| std::env::var("USERNAME")).unwrap_or_default();
    format!("hanami-{user}.sock").to_ns_name::<GenericNamespaced>()
}

/// Becomes the running copy, or hands `request` to the one already running.
/// Returns `None` when another copy took the request.
pub fn claim(request: Request, handle: impl Fn(Request) + Send + 'static) -> io::Result<Option<()>> {
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
        Err(error) if error.kind() == io::ErrorKind::AddrInUse => {
            let mut stream = Stream::connect(name()?)?;
            stream.write_all(format!("{}\n", request.word()).as_bytes())?;
            Ok(None)
        }
        Err(error) => Err(error),
    }
}

#[cfg(test)]
mod tests {
    use super::Request;

    #[test]
    fn words_round_trip() {
        for request in [Request::Open, Request::Toggle, Request::Nothing] {
            assert_eq!(Request::from_word(request.word()), Some(request));
        }
        assert_eq!(Request::from_word("quit"), None);
    }
}
