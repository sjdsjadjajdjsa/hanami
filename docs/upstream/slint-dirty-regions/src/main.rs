//! Many small items moving over a translucent window, with the software
//! renderer and the winit backend.
//!
//! Every 5 seconds it prints:
//! - frames drawn per second (RedrawRequested events) against steps per second,
//! - this process's CPU use (Linux only),
//! - how much of the window three dirty rectangles cover after merging,
//!   worked out with the same merge rule as `DirtyRegion::add_box`, against
//!   the area the moving items really touch.
//!
//! Environment: ITEMS (default 24), STEP_MS (default 33).

use std::cell::{Cell, RefCell};
use std::rc::Rc;
use std::time::{Duration, Instant};

use slint::winit_030::winit::event::WindowEvent;
use slint::winit_030::{EventResult, WinitWindowAccessor};
use slint::{ModelRc, Timer, TimerMode, VecModel};

slint::slint! {
    export struct Item { x: float, speed: float, sway: float, phase: float, size: float }

    export component Demo inherits Window {
        in property <[Item]> items;
        in property <float> t;
        width: 340px;
        height: 440px;
        no-frame: true;
        background: transparent;

        panel := Rectangle {
            border-radius: 16px;
            background: #17141db8;
            border-width: 1px;
            border-color: #ffffff17;
            clip: true;

            for item in root.items: Rectangle {
                width: item.size * 1px;
                height: item.size * 1.2px;
                border-radius: self.width / 2;
                background: #f7c4d3;
                opacity: 0.8;
                x: panel.width * item.x + item.sway * 1px * Math.sin((root.t * 0.9 + item.phase) * 1rad) - self.width / 2;
                y: Math.mod(root.t * item.speed + item.phase * 97, panel.height / 1px + 40) * 1px - 20px;
            }

            VerticalLayout {
                padding: 20px;
                spacing: 8px;
                Text { text: "Rows of text under the moving items"; color: #ece6ee; font-size: 15px; }
                for i in 7: Rectangle {
                    height: 44px;
                    border-radius: 10px;
                    background: i == 0 ? #f4b6c824 : transparent;
                    HorizontalLayout {
                        padding-left: 14px;
                        padding-right: 14px;
                        Text { text: "Row " + (i + 1); color: #ece6ee; font-size: 14px; vertical-alignment: center; }
                        Text { text: "label"; color: #9b93a3; font-size: 11px; horizontal-alignment: right; vertical-alignment: center; }
                    }
                }
            }
        }
    }
}

const WIDTH: f32 = 340.0;
const HEIGHT: f32 = 440.0;

/// The same geometry the .slint code computes, for the dirty-region estimate.
fn item_box(item: &Item, t: f32) -> [f32; 4] {
    let (w, h) = (item.size, item.size * 1.2);
    let x = WIDTH * item.x + item.sway * (t * 0.9 + item.phase).sin() - w / 2.0;
    let y = (t * item.speed + item.phase * 97.0).rem_euclid(HEIGHT + 40.0) - 20.0;
    [x, y, x + w, y + h]
}

fn area(b: &[f32; 4]) -> f32 {
    (b[2] - b[0]).max(0.0) * (b[3] - b[1]).max(0.0)
}

fn union(a: &[f32; 4], b: &[f32; 4]) -> [f32; 4] {
    [a[0].min(b[0]), a[1].min(b[1]), a[2].max(b[2]), a[3].max(b[3])]
}

fn contains(a: &[f32; 4], b: &[f32; 4]) -> bool {
    a[0] <= b[0] && a[1] <= b[1] && a[2] >= b[2] && a[3] >= b[3]
}

fn clip(b: &[f32; 4]) -> [f32; 4] {
    [b[0].max(0.0), b[1].max(0.0), b[2].min(WIDTH), b[3].min(HEIGHT)]
}

/// `DirtyRegion::add_box` from i-slint-core 1.18.1 (partial_renderer.rs),
/// with its limit of `max` rectangles.
fn add_box(rects: &mut Vec<[f32; 4]>, b: [f32; 4], max: usize) {
    let mut i = 0;
    while i < rects.len() {
        if contains(&rects[i], &b) {
            return;
        } else if contains(&b, &rects[i]) {
            rects.swap_remove(i);
            continue;
        }
        i += 1;
    }
    if rects.len() < max {
        rects.push(b);
    } else {
        let best = (0..rects.len())
            .min_by(|&a, &c| {
                let grow = |i: usize| area(&union(&rects[i], &b)) - area(&rects[i]);
                grow(a).partial_cmp(&grow(c)).unwrap()
            })
            .unwrap();
        rects[best] = union(&rects[best], &b);
    }
}

/// Covered share of the window for one step: the merged rectangles (which
/// can overlap, so this is an upper bound like the renderer's own work) and
/// the items' own boxes, old and new position.
fn coverage(items: &[Item], before: f32, now: f32, max: usize) -> (f32, f32) {
    let mut rects = Vec::new();
    let mut exact = 0.0;
    for item in items {
        for b in [clip(&item_box(item, before)), clip(&item_box(item, now))] {
            exact += area(&b);
            add_box(&mut rects, b, max);
        }
    }
    let merged: f32 = rects.iter().map(area).sum();
    let window = WIDTH * HEIGHT;
    ((merged / window).min(1.0), (exact / window).min(1.0))
}

#[cfg(target_os = "linux")]
fn cpu_seconds() -> f64 {
    let stat = std::fs::read_to_string("/proc/self/stat").unwrap_or_default();
    let fields: Vec<&str> = stat.rsplit(')').next().unwrap_or("").split_whitespace().collect();
    let ticks: f64 = fields.get(11..13).map(|f| f.iter().filter_map(|v| v.parse::<f64>().ok()).sum()).unwrap_or(0.0);
    ticks / 100.0
}

#[cfg(not(target_os = "linux"))]
fn cpu_seconds() -> f64 {
    0.0
}

fn env(name: &str, default: u64) -> u64 {
    std::env::var(name).ok().and_then(|v| v.parse().ok()).unwrap_or(default)
}

fn main() -> Result<(), slint::PlatformError> {
    let count = env("ITEMS", 24) as usize;
    let step = Duration::from_millis(env("STEP_MS", 33));

    // Spread over the window, seeded so every run is the same.
    let items: Vec<Item> = (0..count)
        .map(|n| {
            let f = n as f32;
            Item {
                x: (f * 0.618_034).fract(),
                speed: 9.0 + (f * 7.31).rem_euclid(24.0),
                sway: 5.0 + (f * 3.7).rem_euclid(14.0),
                phase: f * 1.7,
                size: 8.0 + (f * 5.3).rem_euclid(10.0),
            }
        })
        .collect();

    let demo = Demo::new()?;
    demo.set_items(ModelRc::new(VecModel::from(items.clone())));

    let frames = Rc::new(Cell::new(0u32));
    let counted = frames.clone();
    demo.window().on_winit_window_event(move |_, event| {
        if let WindowEvent::RedrawRequested = event {
            counted.set(counted.get() + 1);
        }
        EventResult::Propagate
    });

    let started = Instant::now();
    let steps = Rc::new(Cell::new(0u32));
    let last_t = Rc::new(Cell::new(0.0f32));
    // Per-step coverage sums: merged at 3, merged at 16, exact.
    let sums = Rc::new(RefCell::new((0.0f32, 0.0f32, 0.0f32)));

    let clock = Timer::default();
    {
        let demo = demo.as_weak();
        let (steps, last_t, sums, items) = (steps.clone(), last_t.clone(), sums.clone(), items.clone());
        clock.start(TimerMode::Repeated, step, move || {
            let Some(demo) = demo.upgrade() else { return };
            let t = started.elapsed().as_secs_f32();
            let (three, exact) = coverage(&items, last_t.get(), t, 3);
            let (sixteen, _) = coverage(&items, last_t.get(), t, 16);
            let mut s = sums.borrow_mut();
            s.0 += three;
            s.1 += sixteen;
            s.2 += exact;
            last_t.set(t);
            steps.set(steps.get() + 1);
            demo.set_t(t);
        });
    }

    let report = Timer::default();
    let mut cpu_before = cpu_seconds();
    let mut since = Instant::now();
    report.start(TimerMode::Repeated, Duration::from_secs(5), move || {
        let seconds = since.elapsed().as_secs_f64();
        let cpu = cpu_seconds();
        let n = steps.get().max(1) as f32;
        let s = *sums.borrow();
        println!(
            "{count} items: {:.0} frames/s for {:.0} steps/s, CPU {:.1} % of one core; \
             redrawn per step: {:.0} % with 3 rectangles, {:.0} % with 16, {:.0} % for the items alone",
            frames.get() as f64 / seconds,
            steps.get() as f64 / seconds,
            100.0 * (cpu - cpu_before) / seconds,
            100.0 * s.0 / n,
            100.0 * s.1 / n,
            100.0 * s.2 / n,
        );
        frames.set(0);
        steps.set(0);
        *sums.borrow_mut() = (0.0, 0.0, 0.0);
        cpu_before = cpu;
        since = Instant::now();
    });

    demo.run()
}
