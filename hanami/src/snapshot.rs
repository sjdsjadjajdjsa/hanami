//! `hanami --snapshot picture.png`: draws the panel off screen, with sample
//! games, for the README and the site. It never opens a window or looks at
//! the screen, and the PNG keeps the panel's see-through edges.

use std::error::Error;
use std::path::Path;
use std::rc::Rc;
use std::time::Duration;

use slint::platform::software_renderer::{MinimalSoftwareWindow, PremultipliedRgbaColor, RepaintBufferType};
use slint::platform::{Platform, WindowAdapter, WindowEvent};
use slint::{ComponentHandle, ModelRc, PhysicalSize, VecModel};

use crate::{GameRow, HEIGHT, Panel, WIDTH, icons, petals};

/// The site's demo games, with their icons. Hades is pinned, so it comes first.
const SAMPLE: [(&str, &str, &[u8]); 6] = [
    ("Hades", "pinned · epic", include_bytes!("../../site/assets/games/hades.png")),
    ("Celeste", "steam", include_bytes!("../../site/assets/games/celeste.png")),
    ("Dead Cells", "steam", include_bytes!("../../site/assets/games/dead-cells.png")),
    ("Hollow Knight", "gog", include_bytes!("../../site/assets/games/hollow-knight.png")),
    ("OpenTTD", "port", include_bytes!("../../site/assets/games/openttd.png")),
    ("Stardew Valley", "steam", include_bytes!("../../site/assets/games/stardew-valley.png")),
];

struct Offscreen(Rc<MinimalSoftwareWindow>);

impl Platform for Offscreen {
    fn create_window_adapter(&self) -> Result<Rc<dyn WindowAdapter>, slint::PlatformError> {
        Ok(self.0.clone())
    }
}

pub fn render(path: &Path, scale: f32) -> Result<(), Box<dyn Error>> {
    let window = MinimalSoftwareWindow::new(RepaintBufferType::NewBuffer);
    slint::platform::set_platform(Box::new(Offscreen(window.clone())))
        .map_err(|error| format!("couldn't set up off-screen drawing: {error:?}"))?;
    window.dispatch_event(WindowEvent::ScaleFactorChanged { scale_factor: scale });
    let (width, height) = ((WIDTH as f32 * scale) as u32, (HEIGHT as f32 * scale) as u32);
    window.set_size(PhysicalSize::new(width, height));

    let panel = Panel::new()?;
    let rows: Vec<GameRow> = SAMPLE
        .iter()
        .map(|&(name, label, icon)| GameRow {
            name: name.into(),
            label: label.into(),
            icon: icons::from_bytes(icon, (24.0 * scale) as u32).map(slint::Image::from_rgba8).unwrap_or_default(),
            initial: name[..1].into(),
            pinned: label.starts_with("pinned"),
            new: false,
        })
        .collect();
    panel.set_total(rows.len() as i32);
    panel.set_games(ModelRc::new(VecModel::from(rows)));
    panel.set_petals(ModelRc::new(VecModel::from(petals(18, 1.0, 1.0))));
    // The user's own look, when they have settings: the AI can check its work.
    if let Some(path) = crate::config::path().filter(|path| path.exists()) {
        let config = crate::config::load(&path)?;
        if let Err(problem) = crate::theme::apply(&panel, &config.theme, path.parent(), scale) {
            eprintln!("hanami: {problem}");
        }
    }
    panel.set_t(14.0);
    panel.set_selected(1);
    panel.show()?;
    panel.set_shown(true);
    // Let the fade-in finish before drawing.
    std::thread::sleep(Duration::from_millis(250));
    slint::platform::update_timers_and_animations();

    let mut pixels = vec![PremultipliedRgbaColor::default(); (width * height) as usize];
    window.draw_if_needed(|renderer| {
        renderer.render(&mut pixels, width as usize);
    });
    let rgba: Vec<u8> = pixels.iter().flat_map(|p| unpremultiply(*p)).collect();

    let file = std::io::BufWriter::new(std::fs::File::create(path)?);
    let mut encoder = png::Encoder::new(file, width, height);
    encoder.set_color(png::ColorType::Rgba);
    encoder.set_depth(png::BitDepth::Eight);
    encoder.write_header()?.write_image_data(&rgba)?;
    Ok(())
}

fn unpremultiply(p: PremultipliedRgbaColor) -> [u8; 4] {
    if p.alpha == 0 {
        return [0, 0, 0, 0];
    }
    let undo = |c: u8| ((u16::from(c) * 255 + u16::from(p.alpha) / 2) / u16::from(p.alpha)).min(255) as u8;
    [undo(p.red), undo(p.green), undo(p.blue), p.alpha]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unpremultiply_restores_colour() {
        let p = PremultipliedRgbaColor { red: 64, green: 32, blue: 0, alpha: 128 };
        assert_eq!(unpremultiply(p), [128, 64, 0, 128]);
        assert_eq!(unpremultiply(PremultipliedRgbaColor::default()), [0, 0, 0, 0]);
    }
}
