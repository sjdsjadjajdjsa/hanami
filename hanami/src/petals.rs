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
    /// Colours the petals are painted in (multiplied over the picture, so
    /// its shading stays), taken in turn; empty keeps the picture's own.
    pub tints: Vec<Color>,
}

impl Default for Motion {
    fn default() -> Self {
        Self { count: 24, speed: 1.0, size: 1.0, drift: 1.0, spin: 1.0, tints: Vec::new() }
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

/// The i-th number of the Halton sequence in `base`, 0 to 1: a sequence
/// that fills the line evenly instead of bunching like random numbers.
fn halton(mut i: u32, base: u32) -> f32 {
    let (mut result, mut f) = (0.0, 1.0 / base as f32);
    while i > 0 {
        result += f * (i % base) as f32;
        i /= base;
        f /= base as f32;
    }
    result
}

/// The same petals every time, so the panel always looks the same. Small
/// ones are fainter and slower, as if further away. Places come from a
/// Halton sequence, so petals are spread out across and down the panel
/// rather than landing in clumps.
pub fn petals(motion: &Motion) -> Vec<Petal> {
    let mut next = random();
    (0..motion.count.min(200))
        .enumerate()
        .map(|(i, _)| {
            let depth = next();
            let near = depth * depth;
            let tint = motion.tints.get(i % motion.tints.len().max(1)).copied().unwrap_or_default();
            Petal {
                x: halton(i as u32 + 1, 2) * 0.96 + 0.02,
                speed: (9.0 + near * 20.0 + next() * 4.0) * motion.speed,
                sway: (5.0 + next() * 14.0) * motion.drift,
                freq: 0.4 + next() * 0.6,
                spin: (next() - 0.5) * 70.0 * motion.spin,
                size: (8.0 + near * 10.0) * motion.size,
                alpha: 0.5 + near * 0.4 + next() * 0.1,
                phase: next() * std::f32::consts::TAU,
                drop: halton(i as u32 + 1, 3),
                flip: (0.6 + next() * 1.6) * motion.spin,
                tint,
                image: Default::default(),
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
            drop: next(),
            flip: 0.0,
            tint: Color::default(),
            image: Default::default(),
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn petals_are_spread_across_and_down_the_panel() {
        let petals = petals(&Motion::default());
        for slice in 0..8 {
            let (lo, hi) = (slice as f32 / 8.0, (slice + 1) as f32 / 8.0);
            let across = petals.iter().filter(|p| p.x >= lo && p.x < hi).count();
            let down = petals.iter().filter(|p| p.drop >= lo && p.drop < hi).count();
            assert!(across >= 2 && down >= 2, "slice {slice}: {across} across, {down} down");
        }
        assert_eq!(halton(1, 2), 0.5);
        assert_eq!(halton(2, 2), 0.25);
        assert_eq!(halton(3, 2), 0.75);
    }
}
