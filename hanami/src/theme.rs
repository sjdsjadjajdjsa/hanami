//! The look, from the settings' `[theme]` and a `petal.svg` next to the
//! settings file: both are plain text an AI can write, so the `?` prompt
//! can ask for an autumn panel with maple leaves and get one.

use std::path::Path;

use slint::{Color, ComponentHandle, ModelRc, VecModel};

use crate::config::Theme;
use crate::{Panel, Tokens, petals};

/// Petal pictures bigger than this are refused: a petal is a few lines of SVG.
const MAX_SVG_BYTES: u64 = 64 * 1024;
/// The petal is drawn at this size and scaled down, so it stays sharp on 2x screens.
const PETAL_PX: u32 = 64;
/// The sakura petal, for when there is no petal.svg.
const SAKURA: &[u8] = include_bytes!("../../assets/petal.svg");

/// Puts `theme` on `panel`. `dir` is the settings folder, where `petal.svg`
/// may be; `scale` the screen's. A petal file that can't be used is
/// reported and the sakura petal stays.
pub fn apply(panel: &Panel, theme: &Theme, dir: Option<&Path>, scale: f32) -> Result<(), String> {
    let tokens = panel.global::<Tokens>();
    tokens.set_panel(colour(theme.panel));
    tokens.set_text(colour(theme.text));
    tokens.set_dim(colour(theme.dim));
    tokens.set_accent(colour(theme.accent));
    panel.set_petals(ModelRc::new(VecModel::from(petals::petals(theme.petals, theme.speed, theme.size))));
    let px = (PETAL_PX as f32 * scale.max(1.0)) as u32;
    let own = dir.map(|dir| dir.join("petal.svg")).filter(|path| path.exists()).map(|path| petal(&path, px));
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

/// `path` drawn as a petal `px` wide, or why it couldn't be.
fn petal(path: &Path, px: u32) -> Result<slint::Image, String> {
    let size = std::fs::metadata(path).map_err(|e| format!("petal.svg: {e}"))?.len();
    if size > MAX_SVG_BYTES {
        return Err(format!("petal.svg: {} KB is too big for a petal (keep it under 64 KB)", size / 1024));
    }
    let data = std::fs::read(path).map_err(|e| format!("petal.svg: {e}"))?;
    let pixels = crate::icons::svg(&data, px).ok_or("petal.svg: not an SVG picture Hanami can draw")?;
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
        assert!(petal(&path, PETAL_PX).unwrap_err().contains("not an SVG"));
        std::fs::write(&path, vec![b' '; 70 * 1024]).unwrap();
        assert!(petal(&path, PETAL_PX).unwrap_err().contains("too big"));
        assert!(crate::icons::svg(SAKURA, PETAL_PX).is_some());
        std::fs::remove_dir_all(dir).unwrap();
    }
}
