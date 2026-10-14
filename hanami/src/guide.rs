//! The prompt the ? button copies: Hanami's guide plus a few facts about
//! this computer, for any AI that can look around it (Claude Code, Kimi
//! Code, OpenCode, ...). It asks the AI to explain, not to change anything.

use std::path::Path;

pub const GUIDE: &str = include_str!("../../GUIDE.md");

pub fn prompt(settings: Option<&Path>) -> String {
    let version = env!("CARGO_PKG_VERSION");
    let system = match std::env::consts::OS {
        "linux" => "Linux",
        "windows" => "Windows",
        other => other,
    };
    let settings = settings.map_or_else(|| "not created yet".to_string(), |path| path.display().to_string());
    format!(
        "I use Hanami {version}, a small game launcher, on {system}. My Hanami settings file is {settings}.

Please read Hanami's guide below, then look around my computer (only reading things) and tell me, briefly and in plain words:
- what Hanami does and how I open and close it,
- which games it finds on my computer and where they come from (running `hanami --list` shows them),
- how I add my own games or hide ones I don't want,
- what I can customise, including how it looks (the colours and the falling petals are two text files you can write for me; see the guide's part called Changing the look, and follow its rules exactly if I ask for a new look).

Don't change any files or settings yet. End by asking me what I'd like to do.

--- Hanami guide ---

{GUIDE}"
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn prompt_names_the_settings_file_includes_the_guide_and_asks_for_no_changes() {
        let text = prompt(Some(Path::new("/home/a/.config/hanami/config.toml")));
        assert!(text.contains("/home/a/.config/hanami/config.toml"));
        assert!(text.contains("Don't change any files or settings yet."));
        assert!(text.ends_with(GUIDE));
        assert!(prompt(None).contains("not created yet"));
    }

    /// Needs a desktop session; restores whatever was copied before.
    #[test]
    #[ignore]
    fn the_prompt_reaches_the_system_clipboard() {
        let mut clipboard = arboard::Clipboard::new().unwrap();
        let before = clipboard.get_text().ok();
        let text = prompt(None);
        clipboard.set_text(text.clone()).unwrap();
        let mut reader = arboard::Clipboard::new().unwrap();
        assert_eq!(reader.get_text().unwrap(), text);
        if let Some(before) = before {
            clipboard.set_text(before).unwrap();
        }
    }
}
