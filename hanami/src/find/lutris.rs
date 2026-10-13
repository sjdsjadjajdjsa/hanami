//! Games installed through Lutris, read from its database.

use std::path::{Path, PathBuf};

use rusqlite::{Connection, OpenFlags};

use crate::games::{Game, Launch};

const FLATPAK_ID: &str = "net.lutris.Lutris";

pub fn find() -> Vec<Game> {
    let home = dirs::home_dir().unwrap_or_default();
    let native = dirs::data_dir().map(|dir| dir.join("lutris/pga.db"));
    let flatpak = home.join(".var/app").join(FLATPAK_ID).join("data/lutris/pga.db");
    native
        .into_iter()
        .map(|db| (db, false))
        .chain([(flatpak, true)])
        .filter(|(db, _)| db.is_file())
        .flat_map(|(db, flatpak)| installed(&db).into_iter().map(move |(id, name)| game(id, name, flatpak)))
        .collect()
}

fn game(id: i64, name: String, flatpak: bool) -> Game {
    let target = format!("lutris:rungameid/{id}");
    let (program, args) = if flatpak {
        (PathBuf::from("flatpak"), vec!["run".into(), FLATPAK_ID.into(), target])
    } else {
        (PathBuf::from("lutris"), vec![target])
    };
    Game { name, label: "lutris".into(), launch: Launch::Command { program, args, dir: None } }
}

/// Installed games, minus the ones in Lutris's hidden category.
fn installed(db: &Path) -> Vec<(i64, String)> {
    let Ok(conn) = Connection::open_with_flags(db, OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX) else {
        return Vec::new();
    };
    const WITH_HIDDEN: &str = "SELECT id, name FROM games WHERE installed = 1 AND id NOT IN (
        SELECT gc.game_id FROM games_categories gc JOIN categories c ON c.id = gc.category_id WHERE c.name = '.hidden')";
    const PLAIN: &str = "SELECT id, name FROM games WHERE installed = 1";
    let query = |sql: &str| -> rusqlite::Result<Vec<(i64, String)>> {
        let mut statement = conn.prepare(sql)?;
        let rows = statement.query_map([], |row| Ok((row.get(0)?, row.get(1)?)))?;
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
        assert_eq!(installed(&db), [(1, "Celeste".to_string())]);

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
}
