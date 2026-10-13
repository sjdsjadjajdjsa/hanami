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
            let mut child = command.spawn().map_err(describe)?;
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

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

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
