//! The look, from the settings' `[theme]` and a `petal.svg` (or any
//! picture named `petal`) next to the settings file: the text ones an AI
//! can write, so the `?` prompt can ask for an autumn panel with maple
//! leaves and get one; a png can come from a picture AI or anywhere.

use std::path::Path;

use slint::{Color, ComponentHandle, ModelRc, VecModel};

use crate::config::Theme;
use crate::{Panel, Tokens, petals};

/// Petal pictures bigger than this are refused: a petal is a few lines of
/// SVG or a small png.
const MAX_PETAL_BYTES: u64 = 512 * 1024;
/// Picture kinds a petal may be, the first found winning.
const PETAL_KINDS: [&str; 5] = ["svg", "png", "webp", "jpg", "jpeg"];
/// The petal is drawn at this size and scaled down, so it stays sharp on 2x screens.
const PETAL_PX: u32 = 64;
/// The sakura petal, for when there is no petal.svg.
const SAKURA: &[u8] = include_bytes!("../../assets/petal.svg");

/// Puts `theme` on `panel`. `dir` is the settings folder, where `petal.svg`
/// (or `petal.png`) may be; `scale` the screen's. A petal file that can't
/// be used is reported and the sakura petal stays.
pub fn apply(panel: &Panel, theme: &Theme, dir: Option<&Path>, scale: f32) -> Result<(), String> {
    let tokens = panel.global::<Tokens>();
    tokens.set_panel(colour(theme.panel));
    tokens.set_text(colour(theme.text));
    tokens.set_dim(colour(theme.dim));
    tokens.set_accent(colour(theme.accent));
    let motion = petals::Motion {
        count: theme.petals,
        speed: theme.speed,
        size: theme.size,
        drift: theme.drift,
        spin: theme.spin,
        tints: theme.tints.iter().map(|&c| colour(c)).collect(),
    };
    panel.set_petals(ModelRc::new(VecModel::from(petals::petals(&motion))));
    panel.set_dots(ModelRc::new(VecModel::from(petals::dots(theme.dots))));
    let px = (PETAL_PX as f32 * scale.max(1.0)) as u32;
    let own = dir.and_then(petal_file).map(|path| petal(&path, px));
    let sakura = || slint::Image::from_rgba8(crate::icons::svg(SAKURA, px).expect("the built-in petal draws"));
    match own {
        Some(Ok(image)) => {
            panel.set_petal(image);
            Ok(())
        }
        Some(Err(problem)) => {
            panel.set_petal(sakura());
            Err(problem)
        }
        None => {
            panel.set_petal(sakura());
            Ok(())
        }
    }
}

fn colour(c: crate::config::Colour) -> Color {
    let (r, g, b, a) = c.rgba();
    Color::from_argb_u8(a, r, g, b)
}

/// The petal picture in `dir`, if there is one.
fn petal_file(dir: &Path) -> Option<std::path::PathBuf> {
    PETAL_KINDS.iter().map(|kind| dir.join(format!("petal.{kind}"))).find(|path| path.exists())
}

/// `path` drawn as a petal `px` wide, or why it couldn't be.
fn petal(path: &Path, px: u32) -> Result<slint::Image, String> {
    let name = path.file_name().and_then(|n| n.to_str()).unwrap_or("petal").to_owned();
    let size = std::fs::metadata(path).map_err(|e| format!("{name}: {e}"))?.len();
    if size > MAX_PETAL_BYTES {
        return Err(format!("{name}: {} KB is too big for a petal (keep it under 512 KB)", size / 1024));
    }
    let pixels = crate::icons::decode(path, px).ok_or(format!("{name}: not a picture Hanami can draw"))?;
    Ok(slint::Image::from_rgba8(pixels))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_petal_file_is_drawn_or_refused() {
        let dir = std::env::temp_dir().join(format!("hanami-theme-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("petal.svg");
        std::fs::write(&path, "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 10 10'><circle cx='5' cy='5' r='4' fill='#c40'/></svg>").unwrap();
        let image = petal(&path, PETAL_PX).unwrap();
        assert_eq!(image.size().width, PETAL_PX);
        std::fs::write(&path, "not svg at all").unwrap();
        assert!(petal(&path, PETAL_PX).unwrap_err().contains("not a picture"));
        std::fs::write(&path, vec![b' '; 600 * 1024]).unwrap();
        assert!(petal(&path, PETAL_PX).unwrap_err().contains("too big"));
        assert!(crate::icons::svg(SAKURA, PETAL_PX).is_some());
        assert_eq!(petal_file(&dir).unwrap(), path);
        let png = dir.join("petal.png");
        image::RgbaImage::from_pixel(8, 8, image::Rgba([255, 0, 0, 255])).save(&png).unwrap();
        std::fs::remove_file(&path).unwrap();
        assert_eq!(petal_file(&dir).unwrap(), png);
        assert_eq!(petal(&png, PETAL_PX).unwrap().size().width, PETAL_PX);
        std::fs::remove_dir_all(dir).unwrap();
    }
}
