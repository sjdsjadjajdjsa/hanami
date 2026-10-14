//! The petals inside the panel. Also used by the panel_frames example, so the
//! video shows the same ones.

use crate::Petal;

const COUNT: usize = 18;

/// The same 18 petals every time, so the panel always looks the same.
pub fn petals() -> Vec<Petal> {
    let mut seed: u64 = 0x2545_f491_4f6c_dd1d;
    let mut next = move || {
        seed ^= seed << 13;
        seed ^= seed >> 7;
        seed ^= seed << 17;
        (seed >> 11) as f32 / (1u64 << 53) as f32
    };
    (0..COUNT)
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
