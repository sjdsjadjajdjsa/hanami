//! Desktop glue the toolkit doesn't provide: blur behind the panel on KWin
//! (X11), keeping the panel out of the taskbar, focusing it, and finding
//! where to open it. Each function quietly does nothing where it has no
//! support, so callers never need platform checks.

use raw_window_handle::HasWindowHandle;

/// Horizontal strips that together cover a `width` x `height` rectangle with
/// corners rounded by `radius`, as KWin's blur region (x, y, w, h per strip).
pub fn rounded_region(width: u32, height: u32, radius: u32) -> Vec<u32> {
    let radius = radius.min(width / 2).min(height / 2);
    let mut region = Vec::with_capacity((radius as usize * 2 + 1) * 4);
    for row in 0..radius {
        let dy = radius as f32 - row as f32 - 0.5;
        let inset = (radius as f32 - (radius as f32 * radius as f32 - dy * dy).max(0.0).sqrt()).round() as u32;
        let strip = width - 2 * inset;
        region.extend_from_slice(&[inset, row, strip, 1]);
        region.extend_from_slice(&[inset, height - 1 - row, strip, 1]);
    }
    region.extend_from_slice(&[0, radius, width, height - 2 * radius]);
    region
}

/// Top-left corner that centres a `width` x `height` window on the monitor
/// under the mouse pointer.
pub fn centre_on_pointer(width: u32, height: u32) -> Option<(i32, i32)> {
    imp::centre_on_pointer(width, height)
}

/// Keeps `window` out of the taskbar and pager and above other windows.
/// Call it before every show: X11 window managers forget these states when
/// a window is hidden.
pub fn prepare(window: &(impl HasWindowHandle + ?Sized)) -> bool {
    imp::prepare(window)
}

/// Brings `window` to the front with keyboard focus. Window managers often
/// refuse this to apps (focus stealing prevention); on X11 the request is
/// sent the way pagers and taskbars send it, which KWin honours.
pub fn activate(window: &(impl HasWindowHandle + ?Sized)) -> bool {
    imp::activate(window)
}

/// Asks the compositor to blur what is behind `window`, inside a rounded
/// rectangle. Returns whether the request was accepted.
pub fn blur_behind(window: &(impl HasWindowHandle + ?Sized), width: u32, height: u32, radius: u32) -> bool {
    imp::blur_behind(window, width, height, radius)
}

#[cfg(target_os = "linux")]
mod imp {
    use raw_window_handle::{HasWindowHandle, RawWindowHandle};
    use x11rb::connection::Connection;
    use x11rb::protocol::randr::ConnectionExt as _;
    use x11rb::CURRENT_TIME;
    use x11rb::protocol::xproto::{AtomEnum, ClientMessageEvent, ConnectionExt as _, EventMask, PropMode};
    use x11rb::wrapper::ConnectionExt as _;

    pub fn centre_on_pointer(width: u32, height: u32) -> Option<(i32, i32)> {
        let (conn, screen) = x11rb::connect(None).ok()?;
        let root = conn.setup().roots.get(screen)?.root;
        let pointer = conn.query_pointer(root).ok()?.reply().ok()?;
        let (px, py) = (i32::from(pointer.root_x), i32::from(pointer.root_y));
        let monitors = conn.randr_get_monitors(root, true).ok()?.reply().ok()?.monitors;
        let monitor = monitors.iter().find(|m| {
            let (x, y) = (i32::from(m.x), i32::from(m.y));
            px >= x && py >= y && px < x + i32::from(m.width) && py < y + i32::from(m.height)
        })?;
        Some((
            i32::from(monitor.x) + (i32::from(monitor.width) - width as i32) / 2,
            i32::from(monitor.y) + (i32::from(monitor.height) - height as i32) / 2,
        ))
    }

    fn x11_id(window: &(impl HasWindowHandle + ?Sized)) -> Option<u32> {
        match window.window_handle().ok()?.as_raw() {
            RawWindowHandle::Xlib(h) => Some(h.window as u32),
            RawWindowHandle::Xcb(h) => Some(h.window.get()),
            _ => None,
        }
    }

    fn atoms<const N: usize>(conn: &impl Connection, names: [&[u8]; N]) -> Option<[u32; N]> {
        let cookies: Vec<_> = names.iter().map(|name| conn.intern_atom(false, name).ok()).collect();
        let mut atoms = [0; N];
        for (atom, cookie) in atoms.iter_mut().zip(cookies) {
            *atom = cookie?.reply().ok()?.atom;
        }
        Some(atoms)
    }

    pub fn prepare(window: &(impl HasWindowHandle + ?Sized)) -> bool {
        const ADD: u32 = 1;
        const FROM_APP: u32 = 1;
        let Some(id) = x11_id(window) else { return false };
        let Ok((conn, screen)) = x11rb::connect(None) else { return false };
        let Some(root) = conn.setup().roots.get(screen).map(|s| s.root) else { return false };
        let Some([state, skip_taskbar, skip_pager, above]) = atoms(
            &conn,
            [b"_NET_WM_STATE", b"_NET_WM_STATE_SKIP_TASKBAR", b"_NET_WM_STATE_SKIP_PAGER", b"_NET_WM_STATE_ABOVE"],
        ) else {
            return false;
        };
        // A hidden window carries its wishes in the property, read when it maps;
        // a shown one has to ask the window manager.
        let stored = conn
            .change_property32(PropMode::REPLACE, id, state, AtomEnum::ATOM, &[skip_taskbar, skip_pager, above])
            .ok()
            .is_some_and(|cookie| cookie.check().is_ok());
        let mask = EventMask::SUBSTRUCTURE_REDIRECT | EventMask::SUBSTRUCTURE_NOTIFY;
        let asked = [[ADD, skip_taskbar, skip_pager, FROM_APP, 0], [ADD, above, 0, FROM_APP, 0]].into_iter().all(|data| {
            conn.send_event(false, root, mask, ClientMessageEvent::new(32, id, state, data))
                .ok()
                .is_some_and(|cookie| cookie.check().is_ok())
        });
        stored && asked
    }

    pub fn activate(window: &(impl HasWindowHandle + ?Sized)) -> bool {
        const FROM_PAGER: u32 = 2;
        let Some(id) = x11_id(window) else { return false };
        let Ok((conn, screen)) = x11rb::connect(None) else { return false };
        let Some(root) = conn.setup().roots.get(screen).map(|s| s.root) else { return false };
        let Some(atom) = conn.intern_atom(false, b"_NET_ACTIVE_WINDOW").ok().and_then(|c| c.reply().ok()) else {
            return false;
        };
        let message = ClientMessageEvent::new(32, id, atom.atom, [FROM_PAGER, CURRENT_TIME, 0, 0, 0]);
        let mask = EventMask::SUBSTRUCTURE_REDIRECT | EventMask::SUBSTRUCTURE_NOTIFY;
        conn.send_event(false, root, mask, message).ok().is_some_and(|cookie| cookie.check().is_ok())
    }

    pub fn blur_behind(window: &(impl HasWindowHandle + ?Sized), width: u32, height: u32, radius: u32) -> bool {
        let Some(id) = x11_id(window) else { return false };
        let Ok((conn, _)) = x11rb::connect(None) else { return false };
        let Some(atom) = conn
            .intern_atom(false, b"_KDE_NET_WM_BLUR_BEHIND_REGION")
            .ok()
            .and_then(|cookie| cookie.reply().ok())
        else {
            return false;
        };
        let region = super::rounded_region(width, height, radius);
        // `check` waits for the server: without it the request can be lost
        // when the connection is dropped at the end of this function.
        conn.change_property32(PropMode::REPLACE, id, atom.atom, AtomEnum::CARDINAL, &region)
            .ok()
            .is_some_and(|cookie| cookie.check().is_ok())
    }
}

#[cfg(windows)]
mod imp {
    use raw_window_handle::HasWindowHandle;
    use windows_sys::Win32::Foundation::POINT;
    use windows_sys::Win32::Graphics::Gdi::{GetMonitorInfoW, MONITOR_DEFAULTTONEAREST, MONITORINFO, MonitorFromPoint};
    use windows_sys::Win32::UI::WindowsAndMessaging::GetCursorPos;

    pub fn centre_on_pointer(width: u32, height: u32) -> Option<(i32, i32)> {
        // SAFETY: plain Win32 queries writing into locals that live for the call.
        unsafe {
            let mut pointer = POINT { x: 0, y: 0 };
            if GetCursorPos(&mut pointer) == 0 {
                return None;
            }
            let monitor = MonitorFromPoint(pointer, MONITOR_DEFAULTTONEAREST);
            let mut info: MONITORINFO = std::mem::zeroed();
            info.cbSize = size_of::<MONITORINFO>() as u32;
            if GetMonitorInfoW(monitor, &mut info) == 0 {
                return None;
            }
            let work = info.rcWork;
            Some((
                work.left + (work.right - work.left - width as i32) / 2,
                work.top + (work.bottom - work.top - height as i32) / 2,
            ))
        }
    }

    // Taskbar, rounding and Acrylic are window attributes on Windows, set
    // when the window is created; focus works through winit.
    pub fn prepare(_window: &(impl HasWindowHandle + ?Sized)) -> bool {
        true
    }

    pub fn activate(_window: &(impl HasWindowHandle + ?Sized)) -> bool {
        false
    }

    pub fn blur_behind(_window: &(impl HasWindowHandle + ?Sized), _width: u32, _height: u32, _radius: u32) -> bool {
        false
    }
}

#[cfg(not(any(target_os = "linux", windows)))]
mod imp {
    use raw_window_handle::HasWindowHandle;

    pub fn centre_on_pointer(_width: u32, _height: u32) -> Option<(i32, i32)> {
        None
    }

    pub fn prepare(_window: &(impl HasWindowHandle + ?Sized)) -> bool {
        false
    }

    pub fn activate(_window: &(impl HasWindowHandle + ?Sized)) -> bool {
        false
    }

    pub fn blur_behind(_window: &(impl HasWindowHandle + ?Sized), _width: u32, _height: u32, _radius: u32) -> bool {
        false
    }
}

#[cfg(test)]
mod tests {
    use super::rounded_region;

    #[test]
    fn strips_cover_the_rounded_panel_and_stay_inside_it() {
        let region = rounded_region(340, 440, 16);
        let area: u32 = region.chunks(4).map(|r| r[2] * r[3]).sum();
        let full = 340 * 440;
        assert!(area < full && area > full - 4 * 16 * 16);
        for strip in region.chunks(4) {
            assert!(strip[0] + strip[2] <= 340 && strip[1] + strip[3] <= 440);
        }
    }

    #[test]
    fn radius_is_clamped_to_the_window() {
        let region = rounded_region(20, 10, 16);
        assert!(region.chunks(4).all(|r| r[0] + r[2] <= 20 && r[1] + r[3] <= 10));
    }
}
