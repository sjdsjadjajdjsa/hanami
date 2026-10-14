//! The petals inside the panel. Also used by the panel_frames example, so the
//! video shows the same ones.

use slint::Color;

use crate::Petal;

/// How the petals move and look, from the settings' `[theme]`.
pub struct Motion {
    pub count: u32,
    pub speed: f32,
    pub size: f32,
    pub drift: f32,
    pub spin: f32,
    /// Colours the petals are painted in, taken in turn; empty keeps the
    /// picture's own colours.
    pub tints: Vec<Color>,
}

impl Default for Motion {
    fn default() -> Self {
        Self { count: 18, speed: 1.0, size: 1.0, drift: 1.0, spin: 1.0, tints: Vec::new() }
    }
}

fn random() -> impl FnMut() -> f32 {
    let mut seed: u64 = 0x2545_f491_4f6c_dd1d;
    move || {
        seed ^= seed << 13;
        seed ^= seed >> 7;
        seed ^= seed << 17;
        (seed >> 11) as f32 / (1u64 << 53) as f32
    }
}

/// The same petals every time, so the panel always looks the same. Small
/// ones are fainter and slower, as if further away.
pub fn petals(motion: &Motion) -> Vec<Petal> {
    let mut next = random();
    (0..motion.count.min(200))
        .enumerate()
        .map(|(i, _)| {
            let depth = next();
            let near = depth * depth;
            let tint = motion.tints.get(i % motion.tints.len().max(1)).copied().unwrap_or_default();
            Petal {
                x: next(),
                speed: (9.0 + near * 20.0 + next() * 4.0) * motion.speed,
                sway: (5.0 + next() * 14.0) * motion.drift,
                freq: 0.4 + next() * 0.6,
                spin: (next() - 0.5) * 70.0 * motion.spin,
                size: (6.0 + near * 8.5) * motion.size,
                alpha: 0.35 + near * 0.45 + next() * 0.1,
                phase: next() * std::f32::consts::TAU,
                tint,
            }
        })
        .collect()
}

/// Specks of the accent colour drifting up: pollen, embers, fine snow.
pub fn dots(count: u32) -> Vec<Petal> {
    let mut next = random();
    (0..count.min(100))
        .map(|_| Petal {
            x: next(),
            speed: 4.0 + next() * 7.0,
            sway: 3.0 + next() * 8.0,
            freq: 0.3 + next() * 0.5,
            spin: 0.0,
            size: 2.0 + next() * 2.5,
            alpha: 0.35 + next() * 0.45,
            phase: next() * std::f32::consts::TAU,
            tint: Color::default(),
        })
        .collect()
}
