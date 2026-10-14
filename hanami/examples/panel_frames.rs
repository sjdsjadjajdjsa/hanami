//! Draws the panel off screen, one frame per line of JSON on stdin, for the
//! video docs/video.py makes. A line says what the panel shows at that moment:
//!
//!     {"time": 4.0, "query": "hk", "selected": 0,
//!      "games": [{"name": "Hollow Knight", "label": "gog", "icon": "site/assets/games/hollow-knight.png"}]}
//!
//!     cargo run --release --example panel_frames -- FRAMES_DIR 2.0 < states.jsonl
//!
//! Frames are written as raw premultiplied RGBA, FRAMES_DIR/00000.rgba and on.
//! Time drives the petals and the panel's own animations, so a frame
//! sequence plays back exactly like the app.

#[path = "../src/petals.rs"]
mod petals;

use std::collections::HashMap;
use std::error::Error;
use std::io::{BufRead, Write};
use std::path::{Path, PathBuf};
use std::rc::Rc;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;

use serde::Deserialize;
use slint::platform::software_renderer::{MinimalSoftwareWindow, PremultipliedRgbaColor, RepaintBufferType};
use slint::platform::{Platform, WindowAdapter, WindowEvent};
use slint::{ComponentHandle, Image, PhysicalSize, Rgba8Pixel, SharedPixelBuffer, VecModel};

slint::include_modules!();

const WIDTH: f32 = 340.0;
const HEIGHT: f32 = 440.0;
/// Where the petals start, as in `hanami --snapshot`.
const PETAL_TIME: f32 = 14.0;

/// The video's clock, in microseconds; Slint's animations read it.
static NOW: AtomicU64 = AtomicU64::new(0);

struct Offscreen(Rc<MinimalSoftwareWindow>);

impl Platform for Offscreen {
    fn create_window_adapter(&self) -> Result<Rc<dyn WindowAdapter>, slint::PlatformError> {
        Ok(self.0.clone())
    }

    fn duration_since_start(&self) -> Duration {
        Duration::from_micros(NOW.load(Ordering::Relaxed))
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct State {
    time: f32,
    games: Vec<Row>,
    total: Option<i32>,
    #[serde(default)]
    query: String,
    #[serde(default)]
    selected: i32,
    #[serde(default = "nothing")]
    acting: i32,
    #[serde(default)]
    action: i32,
}

fn nothing() -> i32 {
    -1
}

#[derive(Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
struct Row {
    name: String,
    label: String,
    icon: Option<PathBuf>,
    #[serde(default)]
    pinned: bool,
}

fn icon(path: &Path, px: u32) -> Result<Image, Box<dyn Error>> {
    let picture = image::open(path)?.resize(px, px, image::imageops::FilterType::Lanczos3).into_rgba8();
    let pixels = SharedPixelBuffer::<Rgba8Pixel>::clone_from_slice(picture.as_raw(), picture.width(), picture.height());
    Ok(Image::from_rgba8(pixels))
}

fn main() -> Result<(), Box<dyn Error>> {
    let mut args = std::env::args().skip(1);
    let dir = PathBuf::from(args.next().ok_or("usage: panel_frames FRAMES_DIR [SCALE] < states.jsonl")?);
    let scale: f32 = args.next().map(|s| s.parse()).transpose()?.unwrap_or(2.0);
    std::fs::create_dir_all(&dir)?;

    let window = MinimalSoftwareWindow::new(RepaintBufferType::NewBuffer);
    slint::platform::set_platform(Box::new(Offscreen(window.clone())))
        .map_err(|error| format!("couldn't set up off-screen drawing: {error:?}"))?;
    window.dispatch_event(WindowEvent::ScaleFactorChanged { scale_factor: scale });
    let (width, height) = ((WIDTH * scale) as u32, (HEIGHT * scale) as u32);
    window.set_size(PhysicalSize::new(width, height));

    let panel = Panel::new()?;
    let model = Rc::new(VecModel::<GameRow>::default());
    panel.set_games(model.clone().into());
    panel.set_petals(Rc::new(VecModel::from(petals::petals())).into());
    panel.show()?;
    panel.set_shown(true);

    let mut icons: HashMap<PathBuf, Image> = HashMap::new();
    let mut shown_rows: Vec<Row> = Vec::new();
    let mut pixels = vec![PremultipliedRgbaColor::default(); (width * height) as usize];
    let mut count = 0;
    for line in std::io::stdin().lock().lines() {
        let line = line?;
        if line.trim().is_empty() {
            continue;
        }
        let state: State = serde_json::from_str(&line)?;
        NOW.store((state.time.max(0.0) * 1e6) as u64, Ordering::Relaxed);
        slint::platform::update_timers_and_animations();

        if state.games != shown_rows {
            let mut rows = Vec::new();
            for row in &state.games {
                let picture = match &row.icon {
                    Some(path) => match icons.get(path) {
                        Some(image) => image.clone(),
                        None => {
                            let image = icon(path, (24.0 * scale) as u32)?;
                            icons.insert(path.clone(), image.clone());
                            image
                        }
                    },
                    None => Image::default(),
                };
                rows.push(GameRow {
                    name: row.name.as_str().into(),
                    label: row.label.as_str().into(),
                    icon: picture,
                    initial: row.name.chars().next().map(String::from).unwrap_or_default().into(),
                    pinned: row.pinned,
                    new: false,
                });
            }
            model.set_vec(rows);
            shown_rows = state.games;
        }
        panel.set_total(state.total.unwrap_or(shown_rows.len() as i32));
        panel.set_query(state.query.as_str().into());
        panel.set_selected(state.selected);
        panel.set_acting(state.acting);
        panel.set_action(state.action);
        panel.set_t(PETAL_TIME + state.time);
        slint::platform::update_timers_and_animations();

        window.request_redraw();
        window.draw_if_needed(|renderer| {
            renderer.render(&mut pixels, width as usize);
        });
        let bytes: Vec<u8> = pixels.iter().flat_map(|p| [p.red, p.green, p.blue, p.alpha]).collect();
        std::fs::File::create(dir.join(format!("{count:05}.rgba")))?.write_all(&bytes)?;
        count += 1;
    }
    eprintln!("{count} frames of {width}x{height}");
    Ok(())
}
