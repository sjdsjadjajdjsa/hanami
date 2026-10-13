//! Starting a game so that it outlives Hanami.

use std::io;
use std::process::{Command, Stdio};

use crate::games::Launch;

pub fn start(launch: &Launch) -> Result<(), String> {
    match launch {
        Launch::Open(link) => open::that_detached(link).map_err(describe),
        Launch::Command { program, args, dir } => {
            let mut command = Command::new(program);
            command.args(args).stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null());
            if let Some(dir) = dir {
                command.current_dir(dir);
            }
            detach(&mut command);
            let mut child = match command.spawn() {
                Ok(child) => child,
                #[cfg(windows)]
                Err(error) if shell::needed(&error) => return shell::start(program, args, dir.as_deref()),
                Err(error) => return Err(describe(error)),
            };
            // Reap the game when it exits so it never lingers as a zombie.
            std::thread::spawn(move || child.wait());
            Ok(())
        }
    }
}

fn describe(error: io::Error) -> String {
    match error.kind() {
        io::ErrorKind::NotFound => "program or folder not found".into(),
        io::ErrorKind::PermissionDenied => "not allowed to run it".into(),
        _ => error.to_string(),
    }
}

/// A separate process group, so closing Hanami never takes the game with it.
#[cfg(unix)]
fn detach(command: &mut Command) {
    use std::os::unix::process::CommandExt;
    command.process_group(0);
}

#[cfg(windows)]
fn detach(command: &mut Command) {
    use std::os::windows::process::CommandExt;
    const DETACHED_PROCESS: u32 = 0x0000_0008;
    const CREATE_NEW_PROCESS_GROUP: u32 = 0x0000_0200;
    command.creation_flags(DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP);
}

/// Starting a program the way Explorer does, for what a plain start refuses.
#[cfg(windows)]
mod shell {
    use std::ffi::OsStr;
    use std::io;
    use std::os::windows::ffi::OsStrExt;
    use std::path::Path;
    use std::ptr::{null, null_mut};

    use windows_sys::Win32::UI::Shell::ShellExecuteW;
    use windows_sys::Win32::UI::WindowsAndMessaging::SW_SHOWNORMAL;

    /// The game asks for admin rights, or the command is a shortcut (.lnk, .url).
    pub fn needed(error: &io::Error) -> bool {
        const ELEVATION_REQUIRED: i32 = 740;
        const BAD_EXE_FORMAT: i32 = 193;
        matches!(error.raw_os_error(), Some(ELEVATION_REQUIRED | BAD_EXE_FORMAT))
    }

    pub fn start(program: &Path, args: &[String], dir: Option<&Path>) -> Result<(), String> {
        let wide = |text: &OsStr| text.encode_wide().chain([0]).collect::<Vec<u16>>();
        let params = args.iter().map(|arg| quote(arg)).collect::<Vec<_>>().join(" ");
        let (program, params) = (wide(program.as_os_str()), wide(params.as_ref()));
        let dir = dir.map(|dir| wide(dir.as_os_str()));
        // SAFETY: every string is NUL-terminated and outlives the call.
        let result = unsafe {
            ShellExecuteW(
                null_mut(),
                null(),
                program.as_ptr(),
                params.as_ptr(),
                dir.as_ref().map_or(null(), |dir| dir.as_ptr()),
                SW_SHOWNORMAL,
            )
        };
        // Anything above 32 means it started.
        if result as isize > 32 { Ok(()) } else { Err("Windows couldn't start it".into()) }
    }

    /// One argument as Windows programs split their command line: quoted
    /// when needed, with backslashes doubled before a quote.
    pub fn quote(arg: &str) -> String {
        if !arg.is_empty() && !arg.contains([' ', '\t', '"']) {
            return arg.into();
        }
        let mut quoted = String::from('"');
        let mut slashes = 0;
        for c in arg.chars() {
            match c {
                '\\' => slashes += 1,
                '"' => {
                    quoted.extend(std::iter::repeat_n('\\', slashes * 2 + 1));
                    quoted.push('"');
                    slashes = 0;
                }
                c => {
                    quoted.extend(std::iter::repeat_n('\\', slashes));
                    quoted.push(c);
                    slashes = 0;
                }
            }
        }
        quoted.extend(std::iter::repeat_n('\\', slashes * 2));
        quoted.push('"');
        quoted
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    #[cfg(windows)]
    #[test]
    fn arguments_with_spaces_are_quoted() {
        assert_eq!(shell::quote("-fullscreen"), "-fullscreen");
        assert_eq!(shell::quote("C:\\My Games\\a.cfg"), "\"C:\\My Games\\a.cfg\"");
        assert_eq!(shell::quote(""), "\"\"");
        assert_eq!(shell::quote("C:\\My Games\\"), "\"C:\\My Games\\\\\"");
        assert_eq!(shell::quote("say \"hi\""), "\"say \\\"hi\\\"\"");
    }

    #[test]
    fn missing_program_says_so() {
        let launch = Launch::Command { program: PathBuf::from("/nonexistent/hanami-test"), args: vec![], dir: None };
        assert_eq!(start(&launch), Err("program or folder not found".into()));
    }

    #[cfg(unix)]
    #[test]
    fn started_program_runs_in_its_folder() {
        let dir = std::env::temp_dir().join(format!("hanami-launch-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let launch = Launch::Command {
            program: PathBuf::from("/bin/sh"),
            args: vec!["-c".into(), "pwd > started".into()],
            dir: Some(dir.clone()),
        };
        start(&launch).unwrap();
        let marker = dir.join("started");
        for _ in 0..50 {
            if std::fs::read_to_string(&marker).is_ok_and(|text| !text.is_empty()) {
                break;
            }
            std::thread::sleep(std::time::Duration::from_millis(20));
        }
        let written = std::fs::read_to_string(&marker).unwrap();
        assert_eq!(PathBuf::from(written.trim()).canonicalize().unwrap(), dir.canonicalize().unwrap());
        std::fs::remove_dir_all(dir).unwrap();
    }
}
