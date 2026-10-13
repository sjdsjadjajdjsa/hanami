//! Hanami: a small game launcher that lives in the tray.

// No console window behind the panel on Windows; `attach_console` gives
// command-line use its output back.
#![cfg_attr(windows, windows_subsystem = "windows")]

mod config;
mod find;
mod games;
mod guide;
mod ipc;
mod launch;
mod net;
mod snapshot;

use std::cell::{Cell, RefCell};
use std::path::{Path, PathBuf};
use std::rc::Rc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};

use global_hotkey::hotkey::HotKey;
use global_hotkey::{GlobalHotKeyEvent, GlobalHotKeyManager, HotKeyState};
use slint::winit_030::winit::event::WindowEvent;
use slint::winit_030::winit::window::WindowAttributes;
use slint::winit_030::{EventResult, WinitWindowAccessor};
use slint::{ComponentHandle, ModelRc, PhysicalPosition, Timer, TimerMode, VecModel};

use config::{Config, OnLaunch};
use ipc::Request;

slint::include_modules!();

const WIDTH: u32 = 340;
const HEIGHT: u32 = 440;
const RADIUS: u32 = 16;
const PETALS: usize = 18;
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
                    desktop's shortcut settings if the built-in hotkey
                    can't work there (Wayland)
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
    query: RefCell<String>,
    config: RefCell<Config>,
    config_path: Option<PathBuf>,
    hotkey_problem: Option<String>,
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
    clock: Timer,
    fade: Timer,
    notice_clock: Timer,
    /// Kept alive: on Linux the copied text lasts only as long as this does.
    clipboard: RefCell<Option<arboard::Clipboard>>,
}

impl App {
    fn show(self: &Rc<Self>) {
        if self.open.get() {
            return;
        }
        log("show");
        self.focus_hidden_at.set(None);
        self.open.set(true);
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
        if let Some(problem) = &self.hotkey_problem {
            self.notify(problem.clone());
        }
        self.query.borrow_mut().clear();
        self.refilter();

        let scale = self.panel.window().scale_factor();
        if let Some((x, y)) = desktop::centre_on_pointer(WIDTH, HEIGHT, scale) {
            self.panel.window().set_position(PhysicalPosition::new(x, y));
        }
        self.panel.window().with_winit_window(desktop::prepare);
        self.panel.set_shown(false);
        if let Err(error) = self.panel.show() {
            eprintln!("hanami: couldn't show the panel: {error}");
            self.open.set(false);
            return;
        }
        self.mapped.set(true);
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

    /// Blur, taskbar and focus need the native window, which may not exist yet.
    fn focus(&self) {
        let (width, height) = self.physical_size();
        let radius = (RADIUS as f32 * self.panel.window().scale_factor()) as u32;
        let cut_corners = self.cut_corners;
        let panel = self.panel.as_weak();
        let _ = slint::spawn_local(async move {
            let Some(panel) = panel.upgrade() else { return };
            if let Ok(window) = panel.window().winit_window().await {
                #[cfg(windows)]
                off_taskbar(&window);
                if cut_corners {
                    desktop::cut_corners(&*window, width, height, radius);
                }
                desktop::prepare(&*window);
                desktop::blur_behind(&*window, width, height, radius);
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
                    panel.window().with_winit_window(desktop::prepare);
                }
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

    fn physical_size(&self) -> (u32, u32) {
        let scale = self.panel.window().scale_factor();
        ((WIDTH as f32 * scale) as u32, (HEIGHT as f32 * scale) as u32)
    }

    /// Re-reads the settings and the game list; keeps the last good settings on a mistake.
    fn reload(&self) {
        if let Some(path) = &self.config_path {
            match config::load(path) {
                Ok(config) => *self.config.borrow_mut() = config,
                Err(message) => self.notify(message),
            }
        }
        let config = self.config.borrow();
        let games = games::collect(&config, found(&config));
        self.panel.set_total(games.len() as i32);
        *self.games.borrow_mut() = games;
    }

    fn refilter(&self) {
        let games = self.games.borrow();
        let query = self.query.borrow();
        let shown = games::filter(&games, &query);
        self.rows.set_vec(
            shown
                .iter()
                .map(|&index| GameRow {
                    name: games[index].name.as_str().into(),
                    label: games[index].label.as_str().into(),
                })
                .collect::<Vec<_>>(),
        );
        self.panel.set_query(query.as_str().into());
        self.panel.set_selected(0);
        *self.shown.borrow_mut() = shown;
    }

    fn launch(&self, row: usize) {
        let Some(&index) = self.shown.borrow().get(row) else { return };
        let game = self.games.borrow()[index].clone();
        log(&format!("launch {}", game.name));
        match launch::start(&game.launch) {
            Ok(()) => match self.config.borrow().on_launch {
                OnLaunch::Hide => self.hide(),
                OnLaunch::Keep => {}
                OnLaunch::Quit => {
                    let _ = slint::quit_event_loop();
                }
            },
            Err(reason) => self.notify(format!("Couldn't start {}: {reason}", game.name)),
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
        }
    }
}

/// Every game found in the places the settings name.
fn found(config: &Config) -> Vec<games::Game> {
    let mut seen = Vec::new();
    let mut games = Vec::new();
    for &source in &config.find {
        if !seen.contains(&source) {
            seen.push(source);
            let started = Instant::now();
            games.extend(find::games(source));
            log(&format!("looked in {source:?} in {} ms", started.elapsed().as_millis()));
        }
    }
    games
}

fn with_app(f: impl FnOnce(&Rc<App>)) {
    let app = APP.with_borrow(|app| app.clone());
    if let Some(app) = app {
        f(&app);
    }
}

/// The same 18 petals every time, so the panel always looks the same.
fn petals() -> Vec<Petal> {
    let mut seed: u64 = 0x2545_f491_4f6c_dd1d;
    let mut next = move || {
        seed ^= seed << 13;
        seed ^= seed >> 7;
        seed ^= seed << 17;
        (seed >> 11) as f32 / (1u64 << 53) as f32
    };
    (0..PETALS)
        .map(|_| Petal {
            x: next(),
            speed: 12.0 + next() * 16.0,
            sway: 6.0 + next() * 14.0,
            freq: 0.4 + next() * 0.6,
            spin: (next() - 0.5) * 70.0,
            size: 7.0 + next() * 6.0,
            alpha: 0.35 + next() * 0.45,
            phase: next() * std::f32::consts::TAU,
        })
        .collect()
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
    panel.on_typed(|text| {
        let typed: String = text.chars().filter(|c| !c.is_control()).collect();
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
            }
        })
    });
    // Alt+F4 hides the panel the same way Esc does.
    panel.window().on_close_requested(|| {
        with_app(|app| app.hide());
        slint::CloseRequestResponse::KeepWindowShown
    });
    panel.window().on_winit_window_event(|_, event| {
        if let WindowEvent::Focused(focused) = *event {
            Timer::single_shot(Duration::ZERO, move || with_app(|app| app.focus_changed(focused)));
        }
        EventResult::Propagate
    });
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
    tray.on_quit_app(|| {
        let _ = slint::quit_event_loop();
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

/// The manager must stay alive for the hotkey to keep working.
fn register_hotkey(text: &str) -> Result<GlobalHotKeyManager, String> {
    let hotkey: HotKey = text.parse().map_err(|_| format!("Hotkey \"{text}\" isn't a key Hanami understands."))?;
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
    Ok(manager)
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
        for game in games::collect(&config, found(&config)) {
            println!("{}\t{}", game.name, game.label);
        }
        return Ok(());
    }

    let first = if flag("--hidden") {
        Request::Nothing
    } else if flag("--toggle") {
        Request::Toggle
    } else {
        Request::Open
    };
    let handle = |request| {
        let _ = slint::invoke_from_event_loop(move || with_app(|app| app.handle(request)));
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
    let mut backend = slint::BackendSelector::new().with_winit_window_attributes_hook(window_attributes);
    if cfg!(windows) {
        backend = backend.renderer_name(if gpu { "femtovg" } else { "software" }.into());
    }
    backend.select()?;

    let panel = Panel::new()?;
    let rows = Rc::new(VecModel::default());
    panel.set_games(ModelRc::from(rows.clone()));
    panel.set_petals(ModelRc::from(Rc::new(VecModel::from(petals()))));
    connect_panel(&panel);

    let tray = Tray::new()?;
    connect_tray(&tray, config_path.clone());
    let hotkeys = register_hotkey(&config.hotkey);
    let hotkey_problem = hotkeys.as_ref().err().cloned();
    if let Some(problem) = &hotkey_problem {
        log(problem);
    }

    let app = Rc::new(App {
        panel,
        rows,
        games: RefCell::default(),
        shown: RefCell::default(),
        query: RefCell::default(),
        config: RefCell::new(config),
        config_path,
        hotkey_problem,
        cut_corners: cfg!(windows) && !gpu,
        open: Cell::new(false),
        mapped: Cell::new(false),
        had_focus: Cell::new(false),
        opened_at: Cell::new(Instant::now()),
        focus_hidden_at: Cell::new(None),
        last_toggle: Cell::new(None),
        clock: Timer::default(),
        fade: Timer::default(),
        notice_clock: Timer::default(),
        clipboard: RefCell::new(None),
    });
    if let Some(message) = problem {
        app.notify(message);
    }
    APP.with_borrow_mut(|slot| *slot = Some(app.clone()));
    Timer::single_shot(Duration::ZERO, move || app.handle(first));

    slint::run_event_loop_until_quit()?;
    APP.with_borrow_mut(|slot| slot.take());
    drop((tray, hotkeys));
    Ok(())
}
