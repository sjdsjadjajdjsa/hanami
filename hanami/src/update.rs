//! Says when a newer Hanami is out. Asks GitHub at most once a day, on its
//! own thread, and never downloads or installs anything.

use std::path::{Path, PathBuf};
use std::time::{Duration, SystemTime};

use semver::Version;

use crate::net;

const LATEST: &str = "https://api.github.com/repos/sjdsjadjajdjsa/hanami/releases/latest";
/// Where "Get Hanami x.y.z" takes the user.
pub const RELEASES: &str = "https://github.com/sjdsjadjajdjsa/hanami/releases/latest";
const DAY: Duration = Duration::from_secs(24 * 60 * 60);

/// Looks for a release newer than this build and hands its version to
/// `found`, from a background thread. Nothing happens when `online` is off.
/// The newest tag seen is kept in the cache folder, and that file's age says
/// whether GitHub is asked again.
pub fn check(online: bool, found: impl FnOnce(String) + Send + 'static) {
    let Some(stamp) = stamp_path().filter(|_| online) else { return };
    std::thread::spawn(move || {
        let known =
            std::fs::read_to_string(&stamp).ok().map(|text| text.trim().to_string()).filter(|tag| !tag.is_empty());
        let latest = if due(&stamp, SystemTime::now()) {
            let fetched = match net::get(LATEST) {
                Ok(body) => tag(&body),
                Err(error) => {
                    crate::log(&format!("update check failed: {error}"));
                    None
                }
            };
            let latest = fetched.or(known);
            remember(&stamp, latest.as_deref().unwrap_or(""));
            latest
        } else {
            known
        };
        match latest.as_deref().and_then(|tag| newer(tag, env!("CARGO_PKG_VERSION"))) {
            Some(version) => found(version.to_string()),
            None => crate::log(&format!("no newer version (latest seen: {})", latest.as_deref().unwrap_or("none"))),
        }
        desktop::return_memory();
    });
}

fn stamp_path() -> Option<PathBuf> {
    dirs::cache_dir().map(|dir| dir.join("hanami").join("latest"))
}

/// True when the stamp is missing or older than a day. A stamp from the
/// future (the clock was put back) counts as fresh.
fn due(stamp: &Path, now: SystemTime) -> bool {
    std::fs::metadata(stamp)
        .and_then(|meta| meta.modified())
        .ok()
        .is_none_or(|modified| now.duration_since(modified).unwrap_or(Duration::ZERO) >= DAY)
}

fn remember(stamp: &Path, tag: &str) {
    if let Some(dir) = stamp.parent() {
        let _ = std::fs::create_dir_all(dir);
    }
    let _ = std::fs::write(stamp, tag);
}

/// The `tag_name` of a GitHub release.
fn tag(body: &str) -> Option<String> {
    let release: serde_json::Value = serde_json::from_str(body).ok()?;
    release.get("tag_name")?.as_str().map(str::to_string)
}

/// The version behind a tag like `v0.2.0`, when it is above `current`.
fn newer(tag: &str, current: &str) -> Option<Version> {
    let found = Version::parse(tag.trim().trim_start_matches('v')).ok()?;
    let current = Version::parse(current).ok()?;
    (found > current).then_some(found)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn versions_compare_as_numbers() {
        assert_eq!(newer("v0.2.0", "0.1.2"), Some(Version::new(0, 2, 0)));
        assert_eq!(newer("v0.10.0", "0.9.0"), Some(Version::new(0, 10, 0)));
        assert_eq!(newer("1.0.0", "0.1.2"), Some(Version::new(1, 0, 0)));
        assert_eq!(newer(" v0.1.3\n", "0.1.2"), Some(Version::new(0, 1, 3)));
        assert_eq!(newer("v0.1.2", "0.1.2"), None);
        assert_eq!(newer("v0.1.1", "0.1.2"), None);
        assert_eq!(newer("v1.0.0-rc.1", "1.0.0"), None);
        assert_eq!(newer("latest", "0.1.2"), None);
        assert_eq!(newer("", "0.1.2"), None);
        assert!(newer("v99.0.0", env!("CARGO_PKG_VERSION")).is_some());
    }

    #[test]
    fn tag_comes_from_the_release_json() {
        assert_eq!(tag(r#"{"url": "x", "tag_name": "v0.2.0", "name": "Hanami v0.2.0"}"#), Some("v0.2.0".into()));
        assert_eq!(tag(r#"{"message": "Not Found"}"#), None);
        assert_eq!(tag("<html>rate limited</html>"), None);
    }

    #[test]
    fn checks_once_a_day() {
        let dir = std::env::temp_dir().join(format!("hanami-update-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        let stamp = dir.join("latest");
        let now = SystemTime::now();
        assert!(due(&stamp, now), "no stamp yet");

        remember(&stamp, "v0.1.2");
        assert_eq!(std::fs::read_to_string(&stamp).unwrap(), "v0.1.2");
        assert!(!due(&stamp, now));
        assert!(!due(&stamp, now + DAY - Duration::from_secs(60)));
        assert!(due(&stamp, now + DAY + Duration::from_secs(60)));

        std::fs::File::options().write(true).open(&stamp).unwrap().set_modified(now - 2 * DAY).unwrap();
        assert!(due(&stamp, now));
        let _ = std::fs::remove_dir_all(dir);
    }
}
