//! Hanami: a small game launcher that lives in the tray.

// No console window behind the panel on Windows; `attach_console` gives
// command-line use its output back.
#![cfg_attr(windows, windows_subsystem = "windows")]

mod autostart;
mod config;
mod find;
mod gamepad;
mod games;
mod guide;
#[cfg(all(unix, not(target_vendor = "apple")))]
mod hotkey;
mod icons;
mod ipc;
mod launch;
mod net;
mod petals;
mod snapshot;
mod state;
mod theme;
mod update;

use std::cell::{Cell, RefCell};
use std::collections::HashSet;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::rc::Rc;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};

use global_hotkey::hotkey::HotKey;
use global_hotkey::{GlobalHotKeyEvent, GlobalHotKeyManager, HotKeyState};
use slint::winit_030::winit::event::WindowEvent;
#[cfg(windows)]
use slint::winit_030::winit::event::{ElementState, MouseButton};
use slint::winit_030::winit::event_loop::ActiveEventLoop;
use slint::winit_030::winit::window::{WindowAttributes, WindowId};
use slint::winit_030::{CustomApplicationHandler, EventResult, WinitWindowAccessor};
use slint::{ComponentHandle, Model, ModelRc, PhysicalPosition, Timer, TimerMode, VecModel};

use config::{Config, OnLaunch};
use find::Source;
use gamepad::Action;
use games::key;
use ipc::Request;
use petals::petals;
use state::State;

slint::include_modules!();

const WIDTH: u32 = 340;
const HEIGHT: u32 = 440;
const RADIUS: u32 = 16;
/// Icons are 24 px in the row, decoded at twice that for sharp HiDPI.
const ICON_PX: u32 = 48;
const FRAME: Duration = Duration::from_millis(33);
const NOTICE: Duration = Duration::from_secs(4);
/// Matches the fade in hanami.slint.
const FADE: Duration = Duration::from_millis(140);
/// Key repeat and double presses inside this window count once.
const DEBOUNCE: Duration = Duration::from_millis(250);
/// Window managers may move focus around while a window maps.
const SETTLE: Duration = Duration::from_millis(250);
/// Pressing the hotkey or clicking the tray icon takes focus from the panel
/// a moment before the press itself arrives. A toggle this soon after a
/// focus-loss hide belongs to the same press and must not reopen the panel.
const SAME_PRESS: Duration = Duration::from_millis(400);

const HELP: &str = "\
hanami: a small game launcher

  hanami            open the panel (starts Hanami if it isn't running)
  hanami --hidden   start in the tray without opening the panel
  hanami --toggle   open or hide the panel; bind this to a key in your
                    desktop's shortcut settings on a Wayland desktop
                    other than KDE Plasma or GNOME
  hanami --quit     close the running Hanami
  hanami --list     print the games the panel would show
  hanami --guide    print the prompt the ? button copies, for your AI
  hanami --verbose  print what happens, for bug reports
  hanami --snapshot FILE.png
                    draw the panel with sample games into a picture
";

thread_local! {
    static APP: RefCell<Option<Rc<App>>> = const { RefCell::new(None) };
}

static VERBOSE: AtomicBool = AtomicBool::new(false);

thread_local! {
    /// Places that are there but couldn't be read, each said once.
    static PROBLEMS: RefCell<Vec<String>> = const { RefCell::new(Vec::new()) };
}

fn log(what: &str) {
    if VERBOSE.load(Ordering::Relaxed) {
        eprintln!("hanami {:>8.3}s {what}", started().elapsed().as_secs_f32());
    }
}

fn started() -> Instant {
    static START: std::sync::OnceLock<Instant> = std::sync::OnceLock::new();
    *START.get_or_init(Instant::now)
}

struct App {
    panel: Panel,
    rows: Rc<VecModel<GameRow>>,
    games: RefCell<Vec<games::Game>>,
    shown: RefCell<Vec<usize>>,
    /// Name keys of found games the user hasn't said yes or no to yet.
    fresh: RefCell<HashSet<String>>,
    state: RefCell<State>,
    query: RefCell<String>,
    /// The launcher row that is open, showing the games listed under it.
    folder: RefCell<Option<String>>,
    config: RefCell<Config>,
    config_path: Option<PathBuf>,
    /// Why the hotkey can't work; said once, the first time the panel is open.
    hotkey_problem: RefCell<Option<String>>,
    /// The panel is open or opening (it may still be fading).
    open: Cell<bool>,
    /// The window is on screen (true during the fade-out too).
    mapped: Cell<bool>,
    had_focus: Cell<bool>,
    opened_at: Cell<Instant>,
    focus_hidden_at: Cell<Option<Instant>>,
    last_toggle: Cell<Option<Instant>>,
    /// The CPU renderer can't draw see-through on Windows, so the window
    /// itself is cut to the panel's rounded shape.
    cut_corners: bool,
    controller: Arc<gamepad::Controller>,
    clock: Timer,
    fade: Timer,
    notice_clock: Timer,
    /// Kept alive: on Linux the copied text lasts only as long as this does.
    clipboard: RefCell<Option<arboard::Clipboard>>,
    icons: icons::Icons,
    /// Said once, the next time the panel is open.
    update_notice: RefCell<Option<String>>,
}

impl App {
    fn show(self: &Rc<Self>) {
        if self.open.get() {
            return;
        }
        log("show");
        self.focus_hidden_at.set(None);
        self.open.set(true);
        self.panel.set_acting(-1);
        self.panel.set_renaming(-1);
        self.controller.set_open(true);
        self.had_focus.set(false);
        self.opened_at.set(Instant::now());
        self.fade.stop();

        if self.mapped.get() {
            // Caught mid fade-out: fade straight back in.
            self.panel.set_shown(true);
            self.focus();
            return;
        }

        self.reload();
        // One notice at a time; the others wait for the next open.
        if let Some(problem) = self.hotkey_problem.take() {
            self.notify(problem);
        } else if let Some(problem) =
            PROBLEMS.with_borrow_mut(|problems| (!problems.is_empty()).then(|| problems.remove(0)))
        {
            self.notify(format!("Couldn't read {problem}"));
        } else if let Some(message) = self.update_notice.take() {
            self.notify(message);
        }
        self.query.borrow_mut().clear();
        *self.folder.borrow_mut() = None;
        self.refilter();

        let scale = self.panel.window().scale_factor();
        if let Some((x, y)) = desktop::centre_on_pointer(WIDTH, HEIGHT, scale) {
            self.panel.window().set_position(PhysicalPosition::new(x, y));
        }
        self.panel.window().with_winit_window(|window| desktop::prepare(window, u64::from(window.id())));
        self.panel.set_shown(false);
        if let Err(error) = self.panel.show() {
            eprintln!("hanami: couldn't show the panel: {error}");
            self.open.set(false);
            return;
        }
        self.mapped.set(true);
        // A window that started hidden has never drawn, so nothing marks it
        // dirty; on Wayland a surface without a first frame is never mapped.
        self.panel.window().request_redraw();
        self.panel.invoke_focus_keys();

        let app = Rc::downgrade(self);
        self.clock.start(TimerMode::Repeated, FRAME, move || {
            if let Some(app) = app.upgrade() {
                app.panel.set_t(started().elapsed().as_secs_f32());
            }
        });
        // Start the fade on the next frame, once the window has drawn at 0.
        let panel = self.panel.as_weak();
        Timer::single_shot(Duration::from_millis(16), move || {
            if let Some(panel) = panel.upgrade() {
                panel.set_shown(true);
            }
        });
        self.focus();
    }

    /// Blur, taskbar and focus need the native window, which may not exist
    /// yet, and neither does its real scale before then.
    fn focus(&self) {
        let guessed = self.panel.window().scale_factor();
        let cut_corners = self.cut_corners;
        let panel = self.panel.as_weak();
        let _ = slint::spawn_local(async move {
            let Some(panel) = panel.upgrade() else { return };
            if let Ok(window) = panel.window().winit_window().await {
                let scale = panel.window().scale_factor();
                // The very first show centres the panel before the window,
                // and so its scale, exists.
                if scale != guessed
                    && let Some((x, y)) = desktop::centre_on_pointer(WIDTH, HEIGHT, scale)
                {
                    panel.window().set_position(PhysicalPosition::new(x, y));
                }
                let (width, height) = physical_size(scale);
                let radius = (RADIUS as f32 * scale) as u32;
                #[cfg(windows)]
                off_taskbar(&window);
                if cut_corners {
                    desktop::cut_corners(&*window, width, height, radius);
                }
                let id = u64::from(window.id());
                desktop::prepare(&*window, id);
                desktop::blur_behind(&*window, id, WIDTH, HEIGHT, RADIUS, scale);
                if !desktop::activate(&*window) {
                    window.focus_window();
                }
            }
        });
    }

    fn hide(&self) {
        if !self.open.get() {
            return;
        }
        log("hide");
        self.open.set(false);
        self.controller.set_open(false);
        self.had_focus.set(false);
        self.panel.set_shown(false);
        let panel = self.panel.as_weak();
        self.fade.start(TimerMode::SingleShot, FADE, move || {
            with_app(|app| {
                if app.open.get() {
                    return;
                }
                app.clock.stop();
                app.mapped.set(false);
                if let Some(panel) = panel.upgrade() {
                    let _ = panel.hide();
                    // Hidden X11 windows lose their states; restore them for the next show.
                    panel.window().with_winit_window(|window| desktop::prepare(window, u64::from(window.id())));
                }
                desktop::return_memory();
            })
        });
    }

    fn toggle(self: &Rc<Self>) {
        let now = Instant::now();
        if self.last_toggle.get().is_some_and(|last| now - last < DEBOUNCE) {
            log("toggle ignored (too soon)");
            return;
        }
        self.last_toggle.set(Some(now));
        if self.open.get() {
            self.hide();
        } else if self.focus_hidden_at.take().is_some_and(|hidden| now - hidden < SAME_PRESS) {
            log("toggle: the same press already hid the panel");
        } else {
            self.show();
        }
    }

    /// Losing focus hides the panel, but only once it really had focus and
    /// has been open long enough for the window manager to settle.
    fn focus_changed(&self, focused: bool) {
        log(if focused { "focus in" } else { "focus out" });
        if focused {
            self.had_focus.set(true);
        } else if self.open.get()
            && self.had_focus.get()
            && self.opened_at.get().elapsed() > SETTLE
            && self.config.borrow().on_launch != OnLaunch::Keep
        {
            self.hide();
            self.focus_hidden_at.set(Some(Instant::now()));
        }
    }

    /// Re-reads the settings and the game list; keeps the last good settings on a mistake.
    fn reload(&self) {
        if let Some(path) = &self.config_path {
            match config::load(path) {
                Ok(config) => *self.config.borrow_mut() = config,
                Err(message) => self.notify(message),
            }
        }
        self.controller.set_enabled(self.config.borrow().controller);
        let dir = self.config_path.as_deref().and_then(Path::parent);
        if let Err(problem) =
            theme::apply(&self.panel, &self.config.borrow().theme, dir, self.panel.window().scale_factor())
        {
            log(&problem);
            PROBLEMS.with_borrow_mut(|problems| {
                if !problems.contains(&problem) {
                    problems.push(problem);
                }
            });
        }
        let (games, fresh) = listed(&self.config.borrow(), &self.state.borrow());
        log(&format!("{} games, {} new", games.len(), fresh.len()));
        self.panel.set_fresh(fresh.len() as i32);
        *self.games.borrow_mut() = games;
        *self.fresh.borrow_mut() = fresh;
    }

    /// The rows for the panel: the whole list (games under a launcher only
    /// when searching), or an open launcher's row and its games.
    fn refilter(&self) {
        let games = self.games.borrow();
        let fresh = self.fresh.borrow();
        let favourites: HashSet<String> = self.config.borrow().favourites.iter().map(|name| key(name)).collect();
        let query = self.query.borrow();
        let folder = {
            let mut folder = self.folder.borrow_mut();
            // A launcher row that went away (hidden, renamed) closes.
            if folder.as_ref().is_some_and(|name| !games.iter().any(|game| game.group.is_none() && &game.name == name))
            {
                *folder = None;
            }
            folder.clone()
        };
        let opens: HashSet<&str> = games.iter().filter_map(|game| game.group.as_deref()).collect();
        let launcher =
            folder.as_ref().and_then(|name| games.iter().position(|game| game.group.is_none() && &game.name == name));
        let inside: Vec<usize> = (0..games.len())
            .filter(|&index| match &folder {
                Some(name) => games[index].group.as_ref() == Some(name),
                None => !query.is_empty() || games[index].group.is_none(),
            })
            .collect();
        // What a search looks through, so "N of M" never has N above M.
        let total = inside.len();
        let pool: Vec<games::Game> = inside.iter().map(|&index| games[index].clone()).collect();
        let mut shown: Vec<usize> = games::filter(&pool, &query).into_iter().map(|at| inside[at]).collect();
        // The launcher's own row leads its list, but not a search in it.
        let head = launcher.filter(|_| query.is_empty());
        shown.splice(0..0, head);
        self.rows.set_vec(
            shown
                .iter()
                .map(|&index| {
                    let game = &games[index];
                    let name = key(&game.name);
                    let (new, pinned) = (fresh.contains(&name), favourites.contains(&name));
                    let mark = if new {
                        "new"
                    } else if pinned {
                        "pinned"
                    } else {
                        ""
                    };
                    let label = match (&game.group, Some(index) == launcher) {
                        (_, true) => "open launcher".to_owned(),
                        (Some(group), false) if folder.is_none() => format!("in {group}"),
                        _ => game.label.clone(),
                    };
                    let label = match (mark, label.as_str()) {
                        ("", label) | (label, "") => label.to_owned(),
                        (mark, label) => format!("{mark} · {label}"),
                    };
                    let initial = game.name.chars().find(|c| c.is_alphanumeric()).map(|c| c.to_uppercase().to_string());
                    GameRow {
                        name: game.name.as_str().into(),
                        label: label.into(),
                        icon: game.icon.as_deref().and_then(|path| self.icons.get(path)).unwrap_or_default(),
                        initial: initial.unwrap_or_default().into(),
                        pinned,
                        new,
                        opens: folder.is_none() && game.group.is_none() && opens.contains(game.name.as_str()),
                    }
                })
                .collect::<Vec<_>>(),
        );
        self.panel.set_total(total as i32);
        self.panel.set_folder(folder.unwrap_or_default().into());
        self.panel.set_query(query.as_str().into());
        // In a launcher, its most recently played game, right after the
        // launcher's own row; while searching, the best match.
        self.panel.set_selected(if head.is_some() && shown.len() > 1 { 1 } else { 0 });
        *self.shown.borrow_mut() = shown;
    }

    /// A background search for ports finished with something new: show it,
    /// unless the user is in the middle of renaming or picking an action.
    fn ports_changed(&self) {
        if !self.open.get() || self.panel.get_renaming() >= 0 || self.panel.get_acting() >= 0 {
            return;
        }
        // Keep the highlight on the game the user moved to; otherwise stay on top.
        let selected = self.panel.get_selected();
        let picked = if selected > 0 { self.game(selected).map(|game| game.name) } else { None };
        self.relist(&picked.unwrap_or_default());
    }

    /// Puts pictures that finished loading into the rows already showing,
    /// without touching the highlight or the search.
    fn show_icons(&self) {
        if !self.mapped.get() {
            return;
        }
        let games = self.games.borrow();
        for (row, &index) in self.shown.borrow().iter().enumerate() {
            let Some(mut data) = self.rows.row_data(row) else { continue };
            if data.icon.size().width > 0 {
                continue;
            }
            if let Some(icon) = games[index].icon.as_deref().and_then(|path| self.icons.peek(path)) {
                data.icon = icon;
                self.rows.set_row_data(row, data);
            }
        }
    }

    /// The game on `row` of the panel.
    fn game(&self, row: i32) -> Option<games::Game> {
        let index = *self.shown.borrow().get(usize::try_from(row).ok()?)?;
        self.games.borrow().get(index).cloned()
    }

    /// Shows the list again after a change, with `name` highlighted.
    fn relist(&self, name: &str) {
        self.reload();
        self.refilter();
        let games = self.games.borrow();
        if let Some(row) = self.shown.borrow().iter().position(|&index| key(&games[index].name) == key(name)) {
            self.panel.set_selected(row as i32);
        }
    }

    fn edit_settings(&self, change: impl FnOnce(&mut toml_edit::DocumentMut)) -> bool {
        let Some(path) = &self.config_path else {
            return false;
        };
        match config::edit(path, change) {
            Ok(()) => true,
            Err(message) => {
                self.notify(message);
                false
            }
        }
    }

    fn save_state(&self) {
        if let Err(message) = self.state.borrow().save() {
            log(&format!("couldn't save what was played: {message}"));
        }
    }

    /// "Pin to top" and "Unpin", or "Keep" for a new find.
    fn pin(&self, row: i32) {
        let Some(game) = self.game(row) else { return };
        let name = key(&game.name);
        if self.fresh.borrow().contains(&name) {
            self.state.borrow_mut().kept.insert(name);
            self.save_state();
        } else {
            let pinned = self.config.borrow().favourites.iter().any(|favourite| key(favourite) == name);
            if !self.edit_settings(|doc| {
                if pinned {
                    config::remove_name(doc, "favourites", &game.name);
                } else {
                    config::add_name(doc, "favourites", &game.name);
                }
            }) {
                return;
            }
        }
        self.relist(&game.name);
    }

    fn rename(&self, row: i32, name: &str) {
        let Some(game) = self.game(row) else { return };
        let name = name.trim();
        if name.is_empty() || name == game.name {
            return;
        }
        let original = games::original_name(&self.config.borrow(), &game.name).to_owned();
        if !self.edit_settings(|doc| config::rename(doc, &original, &game.name, name)) {
            return;
        }
        {
            let mut state = self.state.borrow_mut();
            if self.fresh.borrow().contains(&key(&game.name)) {
                state.kept.insert(key(&game.name));
            }
            state.renamed(&game.name, name);
        }
        self.save_state();
        self.relist(name);
    }

    fn hide_game(&self, row: i32) {
        let Some(game) = self.game(row) else { return };
        if self.edit_settings(|doc| config::add_name(doc, "hide", &game.name)) {
            self.relist("");
            self.notify(format!("Hid {}. It's listed under hide in the settings.", game.name));
        }
    }

    fn keep_new(&self) {
        let fresh = self.fresh.borrow().clone();
        self.state.borrow_mut().kept.extend(fresh);
        self.save_state();
        self.relist("");
    }

    fn hide_new(&self) {
        let names: Vec<String> = {
            let fresh = self.fresh.borrow();
            self.games
                .borrow()
                .iter()
                .filter(|game| fresh.contains(&key(&game.name)))
                .map(|game| game.name.clone())
                .collect()
        };
        if self.edit_settings(|doc| names.iter().for_each(|name| config::add_name(doc, "hide", name))) {
            self.relist("");
            self.notify("Hidden. They're listed under hide in the settings.".into());
        }
    }

    /// Asks for a program with the system's file picker, then adds it and
    /// lets the user name it.
    fn pick_game(&self) {
        log("asking for a program");
        self.hide();
        std::thread::spawn(|| {
            let picked = rfd::FileDialog::new().set_title("Pick a game's program").pick_file();
            log(&format!("picked {picked:?}"));
            if let Some(path) = picked {
                let _ = slint::invoke_from_event_loop(move || with_app(|app| app.add_game(&path)));
            }
        });
    }

    fn add_game(self: &Rc<Self>, program: &Path) {
        let name = games::readable(program);
        let name = {
            let config = self.config.borrow();
            let taken = |name: &str| {
                self.games.borrow().iter().any(|game| key(&game.name) == key(name))
                    || config.hide.iter().any(|hidden| key(hidden) == key(name))
            };
            (1..)
                .map(|n| if n == 1 { name.clone() } else { format!("{name} {n}") })
                .find(|name| !taken(name))
                .unwrap_or(name)
        };
        // Back from the file picker first, so a problem saving it is seen.
        self.show();
        if !self.edit_settings(|doc| config::add_game(doc, &name, program, program.parent())) {
            return;
        }
        self.relist(&name);
        self.panel.set_renaming(self.panel.get_selected());
    }

    fn launch(&self, row: usize) {
        let Some(&index) = self.shown.borrow().get(row) else {
            return;
        };
        let game = self.games.borrow()[index].clone();
        if self.folder.borrow().is_none()
            && self.games.borrow().iter().any(|other| other.group.as_ref() == Some(&game.name))
        {
            log(&format!("open {}", game.name));
            // Opening a new launcher row keeps it, like playing a new game does.
            if self.fresh.borrow().contains(&key(&game.name)) {
                self.state.borrow_mut().kept.insert(key(&game.name));
                self.save_state();
                self.reload();
            }
            *self.folder.borrow_mut() = Some(game.name);
            self.query.borrow_mut().clear();
            self.refilter();
            self.panel.invoke_focus_keys();
            return;
        }
        log(&format!("launch {}", game.name));
        match launch::start(&game.launch) {
            Ok(()) => {
                {
                    let mut state = self.state.borrow_mut();
                    state.played_now(&game.name);
                    if let Some(group) = &game.group {
                        state.played_now(group);
                    }
                    if self.fresh.borrow().contains(&key(&game.name)) {
                        state.kept.insert(key(&game.name));
                    }
                }
                self.save_state();
                self.after_launch();
            }
            Err(reason) => self.notify(format!("Couldn't start {}: {reason}", game.name)),
        }
    }

    /// From a launcher's games back to the whole list, on its row.
    fn back(&self) {
        let Some(folder) = self.folder.borrow_mut().take() else { return };
        log("back");
        self.query.borrow_mut().clear();
        self.refilter();
        self.panel.invoke_focus_keys();
        let games = self.games.borrow();
        if let Some(row) = self.shown.borrow().iter().position(|&index| games[index].name == folder) {
            self.panel.set_selected(row as i32);
        }
    }

    fn after_launch(&self) {
        match self.config.borrow().on_launch {
            OnLaunch::Hide => self.hide(),
            OnLaunch::Keep => {}
            OnLaunch::Quit => {
                let _ = slint::quit_event_loop();
            }
        }
    }

    fn notify(&self, message: String) {
        log(&format!("notice: {message}"));
        self.panel.set_notice(message.into());
        let panel = self.panel.as_weak();
        self.notice_clock.start(TimerMode::SingleShot, NOTICE, move || {
            if let Some(panel) = panel.upgrade() {
                panel.set_notice("".into());
            }
        });
    }

    /// A newer release exists; the tray menu already offers it.
    fn offer_update(&self, version: &str) {
        let message = format!("Hanami {version} is out. Get it from the tray menu.");
        if self.open.get() {
            self.notify(message);
        } else {
            *self.update_notice.borrow_mut() = Some(message);
        }
    }

    fn ask_ai(&self) {
        let prompt = guide::prompt(self.config_path.as_deref());
        let mut clipboard = self.clipboard.borrow_mut();
        if clipboard.is_none() {
            *clipboard = arboard::Clipboard::new().ok();
        }
        let copied = clipboard.as_mut().is_some_and(|clipboard| clipboard.set_text(prompt).is_ok());
        log(&format!("ai prompt copied: {copied}"));
        self.notify(
            if copied { "Copied. Paste it into your AI." } else { "Couldn't copy. Run hanami --guide instead." }.into(),
        );
    }

    fn handle(self: &Rc<Self>, request: Request) {
        log(&format!("request {request:?}"));
        match request {
            Request::Open => self.show(),
            Request::Toggle => self.toggle(),
            Request::Nothing => {}
            Request::Quit => {
                let _ = slint::quit_event_loop();
            }
        }
    }

    /// A controller press, already turned into what it means for the panel.
    fn control(self: &Rc<Self>, action: Action) {
        log(&format!("controller {action:?}"));
        match action {
            Action::Toggle => self.toggle(),
            _ if !self.open.get() => {}
            Action::Hide if self.folder.borrow().is_some() => self.back(),
            Action::Hide => self.hide(),
            Action::Launch => self.launch(self.panel.get_selected() as usize),
            Action::Up | Action::Down => {
                self.panel.set_acting(-1);
                let last = (self.shown.borrow().len() as i32 - 1).max(0);
                let step = if action == Action::Up { -1 } else { 1 };
                self.panel.set_selected((self.panel.get_selected() + step).clamp(0, last));
            }
        }
    }
}

/// Every game for the panel, in the order it shows them, and the name keys
/// of new finds still waiting for a yes or no. Only ports, rewrites and
/// Minecraft launchers ask first (the instances under them don't); a game another place also lists isn't new.
fn listed(config: &Config, state: &State) -> (Vec<games::Game>, HashSet<String>) {
    let mut sources = Vec::new();
    let mut found = Vec::new();
    let mut known: HashSet<String> = config.games.iter().map(|game| key(&game.name)).collect();
    let mut fresh = HashSet::new();
    for &source in &config.find {
        if sources.contains(&source) {
            continue;
        }
        sources.push(source);
        let started = Instant::now();
        let games = find::games(source, config);
        log(&format!("looked in {source:?}: {} games in {} ms", games.len(), started.elapsed().as_millis()));
        for problem in find::problems() {
            log(&problem);
            PROBLEMS.with_borrow_mut(|problems| {
                if !problems.contains(&problem) {
                    problems.push(problem);
                }
            });
        }
        for game in &games {
            let name = key(&game.name);
            if !matches!(source, Source::Ports | Source::Prism) || game.group.is_some() {
                known.insert(name);
            } else if !state.kept.contains(&name) {
                fresh.insert(name);
            }
        }
        found.extend(games);
    }
    let mut games = games::collect(config, found);
    fresh.retain(|name| !known.contains(name) && games.iter().any(|game| key(&game.name) == *name));
    games::order(&mut games, &fresh, &config.favourites, &state.played);
    (games, fresh)
}

/// What a key press adds to the search: letters, digits, spaces and the
/// like. Keys that aren't text (Home, End, F5, ...) arrive as private-use
/// characters and would sit in the search as blanks nothing matches.
fn searchable(text: &str) -> String {
    text.chars().filter(|c| !c.is_control() && !('\u{e000}'..='\u{f8ff}').contains(c)).collect()
}

fn with_app(f: impl FnOnce(&Rc<App>)) {
    let app = APP.with_borrow(|app| app.clone());
    if let Some(app) = app {
        f(&app);
    }
}

/// The panel's size in pixels at `scale`.
fn physical_size(scale: f32) -> (u32, u32) {
    ((WIDTH as f32 * scale) as u32, (HEIGHT as f32 * scale) as u32)
}

/// How the panel's window is created, per platform.
fn window_attributes(attributes: WindowAttributes) -> WindowAttributes {
    #[cfg(all(unix, not(target_vendor = "apple")))]
    let attributes = {
        use slint::winit_030::winit::platform::x11::{WindowAttributesExtX11, WindowType};
        attributes.with_x11_window_type(vec![WindowType::Utility]).with_name("hanami", "Hanami")
    };
    #[cfg(windows)]
    let attributes = {
        use slint::winit_030::winit::platform::windows::{CornerPreference, WindowAttributesExtWindows};
        // Windows 11 would round and outline the whole window, not the panel.
        attributes.with_skip_taskbar(true).with_corner_preference(CornerPreference::DoNotRound).with_border_color(None)
    };
    attributes
}

/// Windows puts the panel back on the taskbar every time it is shown.
#[cfg(windows)]
fn off_taskbar(window: &slint::winit_030::winit::window::Window) {
    use slint::winit_030::winit::platform::windows::WindowExtWindows;
    window.set_skip_taskbar(true);
}

fn connect_panel(panel: &Panel) {
    panel.on_launch(|row| with_app(|app| app.launch(row as usize)));
    panel.on_dismiss(|| with_app(|app| app.hide()));
    panel.on_ask_ai(|| with_app(|app| app.ask_ai()));
    panel.on_add_game(|| with_app(|app| app.pick_game()));
    panel.on_pin(|row| with_app(|app| app.pin(row)));
    panel.on_rename(|row, name| with_app(|app| app.rename(row, &name)));
    panel.on_hide_game(|row| with_app(|app| app.hide_game(row)));
    panel.on_keep_new(|| with_app(|app| app.keep_new()));
    panel.on_hide_new(|| with_app(|app| app.hide_new()));
    panel.on_typed(|text| {
        let typed = searchable(&text);
        if !typed.is_empty() {
            with_app(|app| {
                app.query.borrow_mut().push_str(&typed);
                app.refilter();
            });
        }
    });
    panel.on_erased(|| {
        with_app(|app| {
            if app.query.borrow_mut().pop().is_some() {
                app.refilter();
            } else {
                app.back();
            }
        })
    });
    panel.on_back(|| with_app(|app| app.back()));
    // Alt+F4 hides the panel the same way Esc does.
    panel.window().on_close_requested(|| {
        with_app(|app| app.hide());
        slint::CloseRequestResponse::KeepWindowShown
    });
    #[cfg(windows)]
    let mut held = false;
    panel.window().on_winit_window_event(move |#[cfg_attr(not(windows), allow(unused_variables))] window, event| {
        if let WindowEvent::Focused(focused) = *event {
            Timer::single_shot(Duration::ZERO, move || with_app(|app| app.focus_changed(focused)));
        }
        #[cfg(windows)]
        if drag_with_key(window, event, &mut held) {
            return EventResult::PreventDefault;
        }
        EventResult::Propagate
    });
}

/// Windows has no Alt+drag of its own, so Alt or the Windows key held with the
/// left button down hands the panel to the system's window dragging, as KDE
/// and GNOME do.
/// True when the press was taken and must not reach the panel.
#[cfg(windows)]
fn drag_with_key(window: &slint::Window, event: &WindowEvent, held: &mut bool) -> bool {
    match event {
        WindowEvent::ModifiersChanged(modifiers) => {
            let keys = modifiers.state();
            *held = keys.alt_key() || keys.super_key();
        }
        WindowEvent::Focused(false) => *held = false,
        WindowEvent::MouseInput { state: ElementState::Pressed, button: MouseButton::Left, .. } if *held => {
            window.with_winit_window(|window| {
                let _ = window.drag_window();
            });
            return true;
        }
        _ => {}
    }
    false
}

/// Runs `desktop::prepare` on every native window as soon as it exists.
/// Wayland makes a fresh window for each show, and KDE wants to know before
/// its first frame that it stays out of the taskbar. The tray keeps a window
/// of its own that never shows, and KDE would list even that one.
struct PrepareWindows;

impl CustomApplicationHandler for PrepareWindows {
    fn window_event(
        &mut self,
        _: &ActiveEventLoop,
        id: WindowId,
        window: Option<&slint::winit_030::winit::window::Window>,
        _: Option<&slint::Window>,
        event: &WindowEvent,
    ) -> EventResult {
        // The first configure of a window arrives as a resize; the panel never
        // resizes otherwise.
        match (window, event) {
            (Some(window), WindowEvent::Resized(_)) => {
                desktop::prepare(window, u64::from(id));
            }
            (_, WindowEvent::Destroyed) => desktop::forget(u64::from(id)),
            _ => {}
        }
        EventResult::Propagate
    }
}

fn connect_tray(tray: &Tray, settings: Option<PathBuf>) {
    // A click on the icon toggles; "Open" in its menu always opens.
    tray.on_open_panel(|| with_app(|app| app.toggle()));
    tray.on_show_panel(|| with_app(|app| app.show()));
    tray.on_edit_settings(move || {
        if let Some(path) = &settings
            && let Err(error) = edit(path)
        {
            eprintln!("hanami: couldn't open {}: {error}", path.display());
        }
    });
    if let Err(error) = autostart::refresh() {
        eprintln!("hanami: {error}");
    }
    tray.set_at_login(autostart::enabled());
    let weak = tray.as_weak();
    tray.on_toggle_at_login(move || {
        let Some(tray) = weak.upgrade() else { return };
        let on = !tray.get_at_login();
        match autostart::set(on) {
            Ok(()) => {
                log(if on { "opens at login" } else { "no longer opens at login" });
                tray.set_at_login(on);
            }
            Err(error) => {
                eprintln!("hanami: {error}");
                // The panel is usually closed while the tray menu is used.
                with_app(|app| {
                    app.show();
                    app.notify(error);
                });
            }
        }
    });
    tray.on_quit_app(|| {
        let _ = slint::quit_event_loop();
    });
    tray.on_get_update(|| {
        if let Err(error) = open::that_detached(update::RELEASES) {
            eprintln!("hanami: couldn't open {}: {error}", update::RELEASES);
        }
    });
}

/// Once a day at most, a newer release adds "Get Hanami x.y.z" to the tray
/// menu and one notice in the panel.
fn watch_updates(tray: &Tray, online: bool) {
    let tray = tray.as_weak();
    update::check(online, move |version| {
        let _ = tray.upgrade_in_event_loop(move |tray| {
            log(&format!("newer version: {version}"));
            tray.set_update_version(version.as_str().into());
            with_app(|app| app.offer_update(&version));
        });
    });
}

/// Opens the settings in the user's editor. Windows has none for .toml
/// files until one is picked, so Notepad stands in.
fn edit(path: &Path) -> std::io::Result<()> {
    match open::that_detached(path) {
        #[cfg(windows)]
        Err(_) => std::process::Command::new("notepad.exe").arg(path).spawn().map(drop),
        result => result,
    }
}

/// The manager must stay alive for the hotkey to keep working. On Wayland
/// no app can grab a key itself (registering through Xwayland would succeed
/// and never fire), so the desktop is asked for the key instead, off the
/// UI thread; a problem there reaches the panel as a notice.
fn register_hotkey(text: &str) -> Result<Option<GlobalHotKeyManager>, String> {
    let hotkey: HotKey = text.parse().map_err(|_| format!("Hotkey \"{text}\" isn't a key Hanami understands."))?;
    #[cfg(all(unix, not(target_vendor = "apple")))]
    if std::env::var_os("WAYLAND_DISPLAY").is_some() {
        let text = text.to_owned();
        std::thread::spawn(move || {
            let result = hotkey::bind(&text);
            let _ = slint::invoke_from_event_loop(move || match result {
                Ok(done) => log(&done),
                Err(problem) => {
                    log(&problem);
                    with_app(|app| *app.hotkey_problem.borrow_mut() = Some(problem));
                }
            });
        });
        return Ok(None);
    }
    let manager = GlobalHotKeyManager::new().map_err(|_| {
        "No built-in hotkey here: bind hanami --toggle in your desktop's shortcut settings.".to_string()
    })?;
    manager
        .register(hotkey)
        .map_err(|_| format!("{text} is taken by another app. Pick another hotkey in settings."))?;
    GlobalHotKeyEvent::set_event_handler(Some(|event: GlobalHotKeyEvent| {
        // Holding the keys repeats "pressed"; only the first one counts.
        static HELD: AtomicBool = AtomicBool::new(false);
        match event.state {
            HotKeyState::Pressed if !HELD.swap(true, Ordering::Relaxed) => {
                let _ = slint::invoke_from_event_loop(|| with_app(|app| app.toggle()));
            }
            HotKeyState::Released => HELD.store(false, Ordering::Relaxed),
            HotKeyState::Pressed => {}
        }
    }));
    Ok(Some(manager))
}

/// Windows apps built without a console print nowhere; when started from a
/// terminal, write into that terminal instead.
#[cfg(windows)]
fn attach_console() {
    use windows_sys::Win32::System::Console::{ATTACH_PARENT_PROCESS, AttachConsole};
    // SAFETY: no arguments to get wrong; failure just means no terminal.
    unsafe {
        AttachConsole(ATTACH_PARENT_PROCESS);
    }
}

/// The copy that keeps running lets go of the terminal, so closing the
/// terminal doesn't close Hanami.
#[cfg(windows)]
fn detach_console() {
    use windows_sys::Win32::System::Console::FreeConsole;
    // SAFETY: no arguments; output afterwards goes nowhere, which is fine.
    unsafe {
        FreeConsole();
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    #[cfg(windows)]
    attach_console();
    started();
    let args: Vec<String> = std::env::args().skip(1).collect();
    let flag = |name: &str| args.iter().any(|arg| arg == name);
    if flag("--help") || flag("-h") {
        print!("{HELP}");
        return Ok(());
    }
    VERBOSE.store(flag("--verbose"), Ordering::Relaxed);
    // Before anything else, so the uninstaller's `--quit` never writes settings.
    if flag("--quit") {
        if !ipc::quit_running()? {
            log("Hanami wasn't running");
        }
        return Ok(());
    }

    let config_path = config::path();
    let initial = config_path.as_deref().map(config::load).unwrap_or(Ok(Config::default()));
    let (config, problem) = match initial {
        Ok(config) => (config, None),
        Err(message) => (Config::default(), Some(message)),
    };

    if let Some(position) = args.iter().position(|arg| arg == "--snapshot") {
        let path = args.get(position + 1).ok_or("--snapshot needs a file name, like hanami.png")?;
        snapshot::render(Path::new(path), 2.0)?;
        return Ok(());
    }

    if flag("--guide") {
        print!("{}", guide::prompt(config_path.as_deref()));
        return Ok(());
    }

    if flag("--list") {
        if let Some(message) = &problem {
            eprintln!("{message}");
        }
        if config.find.contains(&Source::Ports) {
            let started = Instant::now();
            let ports = find::scan_ports(&config);
            log(&format!("scanned for ports in {} ms, found {}", started.elapsed().as_millis(), ports.len()));
        }
        let verbose = VERBOSE.load(Ordering::Relaxed);
        let mut out = std::io::stdout().lock();
        for game in listed(&config, &State::load()).0 {
            let label = match &game.group {
                Some(group) => format!("{} · in {group}", game.label),
                None => game.label,
            };
            let written = match (&game.icon, verbose) {
                (Some(icon), true) => writeln!(out, "{}\t{label}\t{}", game.name, icon.display()),
                (None, true) => writeln!(out, "{}\t{label}\t(no icon)", game.name),
                _ => writeln!(out, "{}\t{label}", game.name),
            };
            // The reader went away (`hanami --list | head`): nothing more to say.
            if written.is_err() {
                break;
            }
        }
        PROBLEMS.with_borrow(|problems| {
            for problem in problems {
                eprintln!("hanami: couldn't read {problem}");
            }
        });
        return Ok(());
    }

    let first = if flag("--hidden") {
        Request::Nothing
    } else if flag("--toggle") {
        Request::Toggle
    } else {
        Request::Open
    };
    // Another copy can ask before the event loop exists (Windows checks its
    // OpenGL driver first): wait for it rather than drop the request.
    let handle = |request: Request| {
        for _ in 0..500 {
            match slint::invoke_from_event_loop(move || with_app(|app| app.handle(request))) {
                Err(slint::EventLoopError::NoEventLoopProvider) => std::thread::sleep(Duration::from_millis(20)),
                _ => return,
            }
        }
    };
    if ipc::claim(first, handle)?.is_none() {
        return Ok(());
    }
    #[cfg(windows)]
    if !VERBOSE.load(Ordering::Relaxed) {
        detach_console();
    }

    // Software rendering is the lightest, but Windows only gets a see-through
    // window from a GPU renderer, and that needs a real OpenGL driver.
    // HANAMI_RENDERER=software forces the CPU there.
    let gpu = cfg!(windows)
        && std::env::var("HANAMI_RENDERER").map_or_else(|_| desktop::opengl_works(), |name| name != "software");
    log(if gpu { "drawing with OpenGL" } else { "drawing with the CPU" });
    let mut backend = slint::BackendSelector::new()
        .with_winit_window_attributes_hook(window_attributes)
        .with_winit_custom_application_handler(PrepareWindows);
    if cfg!(windows) {
        backend = backend.renderer_name(if gpu { "femtovg" } else { "software" }.into());
    }
    backend.select()?;

    let panel = Panel::new()?;
    let rows = Rc::new(VecModel::default());
    panel.set_games(ModelRc::from(rows.clone()));
    panel.set_petals(ModelRc::from(Rc::new(VecModel::from(petals(&petals::Motion::default())))));
    connect_panel(&panel);

    // The ports search runs in the background; start it now so the first
    // panel already has its result, and show what it finds while open.
    find::on_ports_change(|| {
        let _ = slint::invoke_from_event_loop(|| with_app(|app| app.ports_changed()));
    });
    if config.find.contains(&Source::Ports) {
        find::games(Source::Ports, &config);
    }

    let tray = Tray::new()?;
    connect_tray(&tray, config_path.clone());
    watch_updates(&tray, config.online);
    let hotkeys = register_hotkey(&config.hotkey);
    let hotkey_problem = hotkeys.as_ref().err().cloned();
    if let Some(problem) = &hotkey_problem {
        log(problem);
    }

    let controller = gamepad::Controller::new(config.controller);
    let app = Rc::new(App {
        panel,
        rows,
        games: RefCell::default(),
        shown: RefCell::default(),
        fresh: RefCell::default(),
        state: RefCell::new(State::load()),
        query: RefCell::default(),
        folder: RefCell::default(),
        config: RefCell::new(config),
        config_path,
        hotkey_problem: RefCell::new(hotkey_problem),
        cut_corners: cfg!(windows) && !gpu,
        open: Cell::new(false),
        mapped: Cell::new(false),
        had_focus: Cell::new(false),
        opened_at: Cell::new(Instant::now()),
        focus_hidden_at: Cell::new(None),
        last_toggle: Cell::new(None),
        controller: controller.clone(),
        clock: Timer::default(),
        fade: Timer::default(),
        notice_clock: Timer::default(),
        clipboard: RefCell::new(None),
        icons: icons::Icons::new(ICON_PX, || {
            let _ = slint::invoke_from_event_loop(|| with_app(|app| app.show_icons()));
        }),
        update_notice: RefCell::new(None),
    });
    if let Some(message) = problem {
        app.notify(message);
    }
    APP.with_borrow_mut(|slot| *slot = Some(app.clone()));
    Timer::single_shot(Duration::ZERO, move || app.handle(first));
    gamepad::start(controller, |action| {
        let _ = slint::invoke_from_event_loop(move || with_app(|app| app.control(action)));
    });

    slint::run_event_loop_until_quit()?;
    APP.with_borrow_mut(|slot| slot.take());
    drop((tray, hotkeys));
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::searchable;

    #[test]
    fn only_text_keys_go_into_the_search() {
        assert_eq!(searchable("h"), "h");
        assert_eq!(searchable(" "), " ");
        assert_eq!(searchable("ł"), "ł");
        for key in ["\u{f700}", "\u{f729}", "\u{f704}", "\t", "\u{1b}"] {
            assert_eq!(searchable(key), "", "{key:?}");
        }
    }
}
