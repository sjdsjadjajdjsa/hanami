//! Games installed through Lutris, read from its database.

use std::path::{Path, PathBuf};

use rusqlite::{Connection, OpenFlags};

use crate::games::{Game, Launch};

const FLATPAK_ID: &str = "net.lutris.Lutris";

pub fn find() -> Vec<Game> {
    let home = dirs::home_dir().unwrap_or_default();
    let native = dirs::data_dir().map(|data| (data, false));
    let flatpak = (home.join(".var/app").join(FLATPAK_ID).join("data"), true);
    native
        .into_iter()
        .chain([flatpak])
        .filter(|(data, _)| data.join("lutris/pga.db").is_file())
        .flat_map(|(data, flatpak)| {
            installed(&data.join("lutris/pga.db")).into_iter().map(move |(id, name, slug)| {
                let mut found = game(id, name, flatpak);
                found.icon = icon(&data, &slug);
                found
            })
        })
        .collect()
}

fn game(id: i64, name: String, flatpak: bool) -> Game {
    let target = format!("lutris:rungameid/{id}");
    let (program, args) = if flatpak {
        (PathBuf::from("flatpak"), vec!["run".into(), FLATPAK_ID.into(), target])
    } else {
        (PathBuf::from("lutris"), vec![target])
    };
    Game { name, label: "lutris".into(), launch: Launch::Command { program, args, dir: None }, icon: None }
}

/// Lutris's icon for a game (in the hicolor theme next to its data folder),
/// or its cover; banners are too wide for a row.
fn icon(data: &Path, slug: &str) -> Option<PathBuf> {
    [
        data.join(format!("icons/hicolor/128x128/apps/lutris_{slug}.png")),
        data.join(format!("lutris/coverart/{slug}.jpg")),
        data.join(format!("lutris/coverart/{slug}.png")),
    ]
    .into_iter()
    .find(|path| path.is_file())
}

/// Installed games (id, name, slug), minus the ones in Lutris's hidden category.
fn installed(db: &Path) -> Vec<(i64, String, String)> {
    let Ok(conn) = Connection::open_with_flags(db, OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX)
    else {
        return Vec::new();
    };
    const WITH_HIDDEN: &str = "SELECT id, name, slug FROM games WHERE installed = 1 AND id NOT IN (
        SELECT gc.game_id FROM games_categories gc JOIN categories c ON c.id = gc.category_id WHERE c.name = '.hidden')";
    const PLAIN: &str = "SELECT id, name, slug FROM games WHERE installed = 1";
    let query = |sql: &str| -> rusqlite::Result<Vec<(i64, String, String)>> {
        let mut statement = conn.prepare(sql)?;
        let rows = statement.query_map([], |row| {
            Ok((row.get(0)?, row.get(1)?, row.get::<_, Option<String>>(2)?.unwrap_or_default()))
        })?;
        rows.collect()
    };
    // Older databases have no categories tables.
    query(WITH_HIDDEN).or_else(|_| query(PLAIN)).unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn installed_games_without_hidden_ones() {
        let db = std::env::temp_dir().join(format!("hanami-lutris-{}.db", std::process::id()));
        let _ = std::fs::remove_file(&db);
        let conn = Connection::open(&db).unwrap();
        conn.execute_batch(
            "CREATE TABLE games (id INTEGER PRIMARY KEY, name TEXT, slug TEXT, installed INTEGER);
             CREATE TABLE categories (id INTEGER PRIMARY KEY, name TEXT);
             CREATE TABLE games_categories (game_id INTEGER, category_id INTEGER);
             INSERT INTO games VALUES (1, 'Celeste', 'celeste', 1), (2, 'Not Installed', 'x', 0), (3, 'Hidden One', 'h', 1);
             INSERT INTO categories VALUES (7, '.hidden');
             INSERT INTO games_categories VALUES (3, 7);",
        )
        .unwrap();
        drop(conn);
        assert_eq!(installed(&db), [(1, "Celeste".to_string(), "celeste".to_string())]);

        let old = Connection::open(&db).unwrap();
        old.execute_batch("DROP TABLE games_categories; DROP TABLE categories;").unwrap();
        drop(old);
        assert_eq!(installed(&db).len(), 2);
        std::fs::remove_file(db).unwrap();
    }

    #[test]
    fn launch_command_native_and_flatpak() {
        let Launch::Command { program, args, .. } = game(4, "Celeste".into(), false).launch else { panic!() };
        assert_eq!((program, args), (PathBuf::from("lutris"), vec!["lutris:rungameid/4".to_string()]));
        let Launch::Command { args, .. } = game(4, "Celeste".into(), true).launch else { panic!() };
        assert_eq!(args, ["run", FLATPAK_ID, "lutris:rungameid/4"]);
    }

    #[test]
    fn icon_before_cover() {
        let data = std::env::temp_dir().join(format!("hanami-lutris-{}", std::process::id()));
        let write = |file: &str| {
            let path = data.join(file);
            std::fs::create_dir_all(path.parent().unwrap()).unwrap();
            std::fs::write(&path, "").unwrap();
            path
        };
        assert_eq!(icon(&data, "celeste"), None);
        let cover = write("lutris/coverart/celeste.jpg");
        assert_eq!(icon(&data, "celeste"), Some(cover));
        let png = write("icons/hicolor/128x128/apps/lutris_celeste.png");
        assert_eq!(icon(&data, "celeste"), Some(png));
        std::fs::remove_dir_all(data).unwrap();
    }
}
