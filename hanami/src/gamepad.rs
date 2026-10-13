//! Game controller support: a thread that waits for controller events and
//! turns them into panel actions.
//!
//! The panel opens on Start and Select held together for half a second.
//! The Guide button is out: Steam opens its overlay or Big Picture on it,
//! Windows opens the Game Bar, and Steam often keeps the controller for
//! itself while it runs. Holding one button is common in games. Start and
//! Select together are bound by nothing well known, and the half-second
//! hold keeps a quick press from counting. While the panel is hidden,
//! nothing but that chord does anything.

use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};

use gilrs::{Axis, Button, EventType, Gilrs};

/// Start and Select held together this long open or hide the panel.
const HOLD: Duration = Duration::from_millis(500);
/// A held direction moves again after DELAY, then every STEP.
const DELAY: Duration = Duration::from_millis(400);
const STEP: Duration = Duration::from_millis(120);
/// The stick counts as pushed past ENGAGE and as let go under RELEASE.
const ENGAGE: f32 = 0.5;
const RELEASE: f32 = 0.3;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Action {
    Toggle,
    Up,
    Down,
    Launch,
    Hide,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Input {
    Button(Button, bool),
    /// The left stick's up-down position: 1 is up, -1 is down.
    Stick(f32),
    /// The deadline passed with nothing else happening.
    Tick,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Dir {
    Up,
    Down,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Chord {
    Off,
    Held(Instant),
    Fired,
}

/// Turns presses into actions: the open chord, repeat while held, the
/// stick's dead zone. Fed by the controller thread, tested without one.
#[derive(Debug)]
pub struct Controls {
    dpad: Option<Dir>,
    stick: Option<Dir>,
    repeat: Option<(Dir, Instant)>,
    start: bool,
    select: bool,
    chord: Chord,
}

impl Default for Controls {
    fn default() -> Self {
        Self { dpad: None, stick: None, repeat: None, start: false, select: false, chord: Chord::Off }
    }
}

impl Controls {
    /// `open` says whether the panel is on screen; hidden, only the chord counts.
    pub fn feed(&mut self, input: Input, now: Instant, open: bool) -> Option<Action> {
        match input {
            Input::Button(Button::Start, down) => self.start = down,
            Input::Button(Button::Select, down) => self.select = down,
            Input::Button(Button::DPadUp, down) => self.dpad = Self::toggled(self.dpad, Dir::Up, down),
            Input::Button(Button::DPadDown, down) => self.dpad = Self::toggled(self.dpad, Dir::Down, down),
            Input::Stick(y) => self.stick = Self::stick_dir(self.stick, y),
            Input::Button(..) | Input::Tick => {}
        }

        self.chord = match self.chord {
            Chord::Off if self.start && self.select => Chord::Held(now),
            _ if !(self.start && self.select) => Chord::Off,
            chord => chord,
        };
        if let Chord::Held(since) = self.chord
            && now >= since + HOLD
        {
            self.chord = Chord::Fired;
            return Some(Action::Toggle);
        }

        if !open {
            self.repeat = None;
            return None;
        }
        match input {
            Input::Button(Button::South, true) => return Some(Action::Launch),
            Input::Button(Button::East, true) => return Some(Action::Hide),
            _ => {}
        }

        let dir = self.dpad.or(self.stick);
        match (dir, self.repeat) {
            (None, _) => self.repeat = None,
            (Some(dir), Some((held, next))) if held == dir => {
                if now >= next {
                    self.repeat = Some((dir, now + STEP));
                    return Some(dir.into());
                }
            }
            (Some(dir), _) => {
                self.repeat = Some((dir, now + DELAY));
                return Some(dir.into());
            }
        }
        None
    }

    /// When to feed a Tick if nothing else happens; None means never.
    pub fn deadline(&self) -> Option<Instant> {
        let chord = match self.chord {
            Chord::Held(since) => Some(since + HOLD),
            Chord::Off | Chord::Fired => None,
        };
        let repeat = self.repeat.map(|(_, next)| next);
        match (chord, repeat) {
            (Some(a), Some(b)) => Some(a.min(b)),
            (a, b) => a.or(b),
        }
    }

    fn toggled(current: Option<Dir>, dir: Dir, down: bool) -> Option<Dir> {
        match (down, current) {
            (true, _) => Some(dir),
            (false, Some(held)) if held == dir => None,
            (false, other) => other,
        }
    }

    fn stick_dir(current: Option<Dir>, y: f32) -> Option<Dir> {
        if y > ENGAGE {
            Some(Dir::Up)
        } else if y < -ENGAGE {
            Some(Dir::Down)
        } else if y.abs() < RELEASE || current.is_some_and(|dir| (dir == Dir::Up) != (y > 0.0)) {
            None
        } else {
            current
        }
    }
}

impl From<Dir> for Action {
    fn from(dir: Dir) -> Self {
        match dir {
            Dir::Up => Action::Up,
            Dir::Down => Action::Down,
        }
    }
}

/// What the settings and the panel allow, shared with the controller thread.
pub struct Controller {
    enabled: AtomicBool,
    open: AtomicBool,
}

impl Controller {
    pub fn new(enabled: bool) -> Arc<Self> {
        Arc::new(Self { enabled: AtomicBool::new(enabled), open: AtomicBool::new(false) })
    }

    pub fn set_enabled(&self, enabled: bool) {
        self.enabled.store(enabled, Ordering::Relaxed);
    }

    pub fn set_open(&self, open: bool) {
        self.open.store(open, Ordering::Relaxed);
    }
}

/// Waits for controller events on its own thread, blocking between them,
/// and hands each action to `act`. Controllers plugged in later are picked up.
pub fn start(controller: Arc<Controller>, act: impl Fn(Action) + Send + 'static) {
    let spawned = std::thread::Builder::new().name("controller".into()).spawn(move || {
        let mut gilrs = match Gilrs::new() {
            Ok(gilrs) => gilrs,
            Err(error) => {
                crate::log(&format!("no controller support: {error}"));
                return;
            }
        };
        let mut controls = Controls::default();
        loop {
            let timeout = controls.deadline().map(|at| at.saturating_duration_since(Instant::now()));
            let input = match gilrs.next_event_blocking(timeout) {
                Some(event) => match input_of(event.event) {
                    Some(input) => input,
                    None => {
                        match event.event {
                            EventType::Connected => {
                                crate::log(&format!("controller: {}", gilrs.gamepad(event.id).name()));
                            }
                            // Buttons held on a pad that went away must not stay held.
                            EventType::Disconnected => controls = Controls::default(),
                            _ => {}
                        }
                        continue;
                    }
                },
                None => Input::Tick,
            };
            if !controller.enabled.load(Ordering::Relaxed) {
                controls = Controls::default();
                continue;
            }
            let open = controller.open.load(Ordering::Relaxed);
            if let Some(action) = controls.feed(input, Instant::now(), open) {
                act(action);
            }
        }
    });
    if let Err(error) = spawned {
        crate::log(&format!("no controller thread: {error}"));
    }
}

fn input_of(event: EventType) -> Option<Input> {
    match event {
        EventType::ButtonPressed(button, _) => Some(Input::Button(button, true)),
        EventType::ButtonReleased(button, _) => Some(Input::Button(button, false)),
        EventType::AxisChanged(Axis::LeftStickY, y, _) => Some(Input::Stick(y)),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ms(start: Instant, ms: u64) -> Instant {
        start + Duration::from_millis(ms)
    }

    fn press(button: Button) -> Input {
        Input::Button(button, true)
    }

    fn release(button: Button) -> Input {
        Input::Button(button, false)
    }

    #[test]
    fn a_held_direction_moves_then_repeats() {
        let t = Instant::now();
        let mut c = Controls::default();
        assert_eq!(c.feed(press(Button::DPadDown), t, true), Some(Action::Down));
        assert_eq!(c.deadline(), Some(ms(t, 400)));
        assert_eq!(c.feed(Input::Tick, ms(t, 200), true), None);
        assert_eq!(c.feed(Input::Tick, ms(t, 400), true), Some(Action::Down));
        assert_eq!(c.deadline(), Some(ms(t, 520)));
        assert_eq!(c.feed(Input::Tick, ms(t, 520), true), Some(Action::Down));
        assert_eq!(c.feed(release(Button::DPadDown), ms(t, 600), true), None);
        assert_eq!(c.deadline(), None);
        assert_eq!(c.feed(press(Button::DPadUp), ms(t, 700), true), Some(Action::Up));
    }

    #[test]
    fn changing_direction_starts_over() {
        let t = Instant::now();
        let mut c = Controls::default();
        assert_eq!(c.feed(press(Button::DPadDown), t, true), Some(Action::Down));
        assert_eq!(c.feed(press(Button::DPadUp), ms(t, 100), true), Some(Action::Up));
        assert_eq!(c.deadline(), Some(ms(t, 500)));
        // Letting go of the other button changes nothing.
        assert_eq!(c.feed(release(Button::DPadDown), ms(t, 150), true), None);
        assert_eq!(c.feed(Input::Tick, ms(t, 500), true), Some(Action::Up));
    }

    #[test]
    fn the_stick_has_a_dead_zone() {
        let t = Instant::now();
        let mut c = Controls::default();
        assert_eq!(c.feed(Input::Stick(0.3), t, true), None);
        assert_eq!(c.feed(Input::Stick(-0.45), t, true), None);
        assert_eq!(c.feed(Input::Stick(0.6), t, true), Some(Action::Up));
        // Drifting back a little keeps it held; letting go stops the repeat.
        assert_eq!(c.feed(Input::Stick(0.4), ms(t, 100), true), None);
        assert_eq!(c.feed(Input::Tick, ms(t, 400), true), Some(Action::Up));
        assert_eq!(c.feed(Input::Stick(0.1), ms(t, 450), true), None);
        assert_eq!(c.deadline(), None);
        assert_eq!(c.feed(Input::Stick(-0.9), ms(t, 500), true), Some(Action::Down));
        // Flipping straight through the middle lets go first.
        assert_eq!(c.feed(Input::Stick(0.4), ms(t, 550), true), None);
        assert_eq!(c.deadline(), None);
    }

    #[test]
    fn start_and_select_held_half_a_second_toggle_once() {
        let t = Instant::now();
        let mut c = Controls::default();
        assert_eq!(c.feed(press(Button::Start), t, false), None);
        assert_eq!(c.deadline(), None);
        assert_eq!(c.feed(press(Button::Select), ms(t, 100), false), None);
        assert_eq!(c.deadline(), Some(ms(t, 600)));
        assert_eq!(c.feed(Input::Tick, ms(t, 400), false), None);
        assert_eq!(c.feed(Input::Tick, ms(t, 600), false), Some(Action::Toggle));
        assert_eq!(c.deadline(), None);
        assert_eq!(c.feed(Input::Tick, ms(t, 2000), true), None);
        assert_eq!(c.feed(release(Button::Select), ms(t, 2100), true), None);
        assert_eq!(c.feed(press(Button::Select), ms(t, 2200), true), None);
        assert_eq!(c.feed(Input::Tick, ms(t, 2700), true), Some(Action::Toggle));
    }

    #[test]
    fn letting_go_early_cancels_the_chord() {
        let t = Instant::now();
        let mut c = Controls::default();
        c.feed(press(Button::Select), t, false);
        c.feed(press(Button::Start), t, false);
        assert_eq!(c.feed(release(Button::Start), ms(t, 300), false), None);
        assert_eq!(c.deadline(), None);
        assert_eq!(c.feed(Input::Tick, ms(t, 600), false), None);
    }

    #[test]
    fn hidden_panel_ignores_everything_but_the_chord() {
        let t = Instant::now();
        let mut c = Controls::default();
        for input in
            [press(Button::DPadDown), press(Button::South), press(Button::East), Input::Stick(1.0), press(Button::Mode)]
        {
            assert_eq!(c.feed(input, t, false), None, "{input:?}");
            assert_eq!(c.deadline(), None, "{input:?}");
        }
    }

    #[test]
    fn a_launches_and_b_hides_only_while_open() {
        let t = Instant::now();
        let mut c = Controls::default();
        assert_eq!(c.feed(press(Button::South), t, true), Some(Action::Launch));
        assert_eq!(c.feed(release(Button::South), t, true), None);
        assert_eq!(c.feed(press(Button::East), t, true), Some(Action::Hide));
        assert_eq!(c.feed(press(Button::North), t, true), None);
    }

    #[test]
    fn hiding_drops_a_held_direction() {
        let t = Instant::now();
        let mut c = Controls::default();
        assert_eq!(c.feed(press(Button::DPadDown), t, true), Some(Action::Down));
        assert_eq!(c.feed(Input::Tick, ms(t, 400), false), None);
        assert_eq!(c.deadline(), None);
    }

    #[test]
    fn the_deadline_is_the_nearest() {
        let t = Instant::now();
        let mut c = Controls::default();
        c.feed(press(Button::Start), t, true);
        c.feed(press(Button::Select), t, true);
        c.feed(press(Button::DPadDown), ms(t, 50), true);
        assert_eq!(c.deadline(), Some(ms(t, 450)));
    }
}
