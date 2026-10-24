//! Desktop glue the toolkit doesn't provide: blur behind the panel on KWin
//! (X11 and Wayland) and Windows 11, keeping the panel out of the taskbar, focusing it, and
//! finding where to open it. Each function quietly does nothing where it has
//! no support, so callers never need platform checks.

use raw_window_handle::{HasDisplayHandle, HasWindowHandle};

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

/// Top-left corner, in physical pixels, that centres a window of `width` x
/// `height` logical pixels on the monitor under the mouse pointer. Windows
/// knows each monitor's scale; elsewhere `scale` is used.
pub fn centre_on_pointer(width: u32, height: u32, scale: f32) -> Option<(i32, i32)> {
    imp::centre_on_pointer(width, height, scale)
}

/// Hands memory a finished job freed back to the system. Each thread gets
/// its own pool in glibc, and freed memory stays there otherwise, which adds
/// up for a program that sits in the tray all day.
pub fn return_memory() {
    #[cfg(all(target_os = "linux", target_env = "gnu"))]
    // SAFETY: takes no pointers; it only releases memory that is already free.
    unsafe {
        libc::malloc_trim(0);
    }
}

/// Keeps `window` out of the taskbar and pager and above other windows.
/// Call it before every show: X11 window managers forget these states when
/// a window is hidden. `id` tells windows apart across their lifetimes
/// (the toolkit's window id); `forget` it when the window is destroyed.
pub fn prepare(window: &(impl HasWindowHandle + HasDisplayHandle + ?Sized), id: u64) -> bool {
    imp::prepare(window, id)
}

/// The window with `id` is gone; drops what `prepare` and `blur_behind`
/// kept for it.
pub fn forget(id: u64) {
    imp::forget(id)
}

/// Brings `window` to the front with keyboard focus. Window managers often
/// refuse this to apps (focus stealing prevention); on X11 the request is
/// sent the way pagers and taskbars send it, which KWin honours.
pub fn activate(window: &(impl HasWindowHandle + ?Sized)) -> bool {
    imp::activate(window)
}

/// Whether OpenGL 2 or newer works. Windows without a graphics driver
/// (virtual machines, remote desktop) only has Microsoft's OpenGL 1.1.
pub fn opengl_works() -> bool {
    imp::opengl_works()
}

/// Cuts `window` to a rounded rectangle, for renderers that can't draw
/// see-through corners. Returns whether it worked.
pub fn cut_corners(window: &(impl HasWindowHandle + ?Sized), width: u32, height: u32, radius: u32) -> bool {
    imp::cut_corners(window, width, height, radius)
}

/// Asks the compositor to blur what is behind `window`, inside a rounded
/// rectangle of `width` x `height` logical pixels with `radius` corners,
/// drawn at `scale`. Windows tints its blur (Acrylic) light or dark, after
/// `dark`, and cuts the window to the rounded shape so the blur keeps to
/// it; Acrylic is turned off for now (see `ACRYLIC`). Returns whether the
/// request was accepted.
pub fn blur_behind(
    window: &(impl HasWindowHandle + HasDisplayHandle + ?Sized),
    id: u64,
    width: u32,
    height: u32,
    radius: u32,
    scale: f32,
    dark: bool,
) -> bool {
    imp::blur_behind(window, id, width, height, radius, scale, dark)
}

/// The icon inside a Windows program (or `.ico`, `.dll`) at about `px`
/// pixels, as straight (not premultiplied) RGBA rows with its width and
/// height. None elsewhere, or when the file has no icon.
pub fn exe_icon(path: &std::path::Path, px: u32) -> Option<(u32, u32, Vec<u8>)> {
    imp::exe_icon(path, px)
}

#[cfg(target_os = "linux")]
mod imp {
    use raw_window_handle::{HasDisplayHandle, HasWindowHandle, RawWindowHandle};
    use x11rb::CURRENT_TIME;
    use x11rb::connection::Connection;
    use x11rb::protocol::randr::ConnectionExt as _;
    use x11rb::protocol::xproto::{AtomEnum, ClientMessageEvent, ConnectionExt as _, EventMask, PropMode};
    use x11rb::wrapper::ConnectionExt as _;

    pub fn centre_on_pointer(width: u32, height: u32, scale: f32) -> Option<(i32, i32)> {
        let (width, height) = ((width as f32 * scale) as u32, (height as f32 * scale) as u32);
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

    pub fn prepare(window: &(impl HasWindowHandle + HasDisplayHandle + ?Sized), key: u64) -> bool {
        const ADD: u32 = 1;
        const FROM_APP: u32 = 1;
        let Some(id) = x11_id(window) else { return wayland::prepare(window, key) };
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
        let asked =
            [[ADD, skip_taskbar, skip_pager, FROM_APP, 0], [ADD, above, 0, FROM_APP, 0]].into_iter().all(|data| {
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

    pub fn opengl_works() -> bool {
        true
    }

    pub fn cut_corners(_window: &(impl HasWindowHandle + ?Sized), _width: u32, _height: u32, _radius: u32) -> bool {
        false
    }

    pub fn exe_icon(_path: &std::path::Path, _px: u32) -> Option<(u32, u32, Vec<u8>)> {
        None
    }

    pub fn forget(key: u64) {
        wayland::forget(key);
    }

    pub fn blur_behind(
        window: &(impl HasWindowHandle + HasDisplayHandle + ?Sized),
        key: u64,
        width: u32,
        height: u32,
        radius: u32,
        scale: f32,
        _dark: bool,
    ) -> bool {
        let Some(id) = x11_id(window) else { return wayland::blur_behind(window, key, width, height, radius) };
        let (width, height, radius) =
            ((width as f32 * scale) as u32, (height as f32 * scale) as u32, (radius as f32 * scale) as u32);
        let Ok((conn, _)) = x11rb::connect(None) else { return false };
        let Some(atom) =
            conn.intern_atom(false, b"_KDE_NET_WM_BLUR_BEHIND_REGION").ok().and_then(|cookie| cookie.reply().ok())
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

    /// KDE's own Wayland protocols, spoken over the toolkit's connection:
    /// one plasma surface per window (asking twice is a protocol error that
    /// ends the program) and one blur per window, kept by the toolkit's
    /// window id: a surface made from the toolkit's pointer can't tell when
    /// it has died, and both the pointer and the protocol id get reused. KWin
    /// places new windows in the middle of the screen by itself, as
    /// `centre_on_pointer` does on X11.
    mod wayland {
        use std::cell::RefCell;
        use std::mem::ManuallyDrop;

        use raw_window_handle::{HasDisplayHandle, HasWindowHandle, RawDisplayHandle, RawWindowHandle};
        use wayland_backend::client::{Backend, ObjectId};
        use wayland_client::protocol::wl_compositor::WlCompositor;
        use wayland_client::protocol::wl_region::WlRegion;
        use wayland_client::protocol::wl_registry::{self, WlRegistry};
        use wayland_client::protocol::wl_surface::WlSurface;
        use wayland_client::{Connection, Dispatch, EventQueue, Proxy, QueueHandle, delegate_noop};
        use wayland_protocols_plasma::blur::client::org_kde_kwin_blur::OrgKdeKwinBlur;
        use wayland_protocols_plasma::blur::client::org_kde_kwin_blur_manager::OrgKdeKwinBlurManager;
        use wayland_protocols_plasma::plasma_shell::client::org_kde_plasma_shell::OrgKdePlasmaShell;
        use wayland_protocols_plasma::plasma_shell::client::org_kde_plasma_surface::OrgKdePlasmaSurface;

        /// The globals Hanami uses, each with the name the registry gave it:
        /// KWin takes the blur one away and brings it back as the Blur effect
        /// is turned off and on.
        #[derive(Default)]
        struct Globals {
            compositor: Option<WlCompositor>,
            shell: Option<(u32, OrgKdePlasmaShell)>,
            blur: Option<(u32, OrgKdeKwinBlurManager)>,
        }

        impl Dispatch<WlRegistry, ()> for Globals {
            fn event(
                state: &mut Self,
                registry: &WlRegistry,
                event: wl_registry::Event,
                _: &(),
                _: &Connection,
                qh: &QueueHandle<Self>,
            ) {
                match event {
                    wl_registry::Event::Global { name, interface, version } => match interface.as_str() {
                        "wl_compositor" => state.compositor = Some(registry.bind(name, version.min(4), qh, ())),
                        "org_kde_plasma_shell" => {
                            state.shell = Some((name, registry.bind(name, version.min(8), qh, ())));
                        }
                        "org_kde_kwin_blur_manager" => state.blur = Some((name, registry.bind(name, 1, qh, ()))),
                        _ => {}
                    },
                    wl_registry::Event::GlobalRemove { name } => {
                        if state.shell.as_ref().is_some_and(|(known, _)| *known == name) {
                            state.shell = None;
                        }
                        if state.blur.as_ref().is_some_and(|(known, _)| *known == name) {
                            state.blur = None;
                        }
                    }
                    _ => {}
                }
            }
        }

        delegate_noop!(Globals: ignore WlCompositor);
        delegate_noop!(Globals: ignore WlRegion);
        delegate_noop!(Globals: ignore OrgKdePlasmaShell);
        delegate_noop!(Globals: ignore OrgKdePlasmaSurface);
        delegate_noop!(Globals: ignore OrgKdeKwinBlurManager);
        delegate_noop!(Globals: ignore OrgKdeKwinBlur);

        struct Plasma {
            conn: Connection,
            queue: EventQueue<Globals>,
            globals: Globals,
            surfaces: Vec<(u64, OrgKdePlasmaSurface)>,
            blurs: Vec<(u64, OrgKdeKwinBlur)>,
        }

        thread_local! {
            // Never dropped: dropping would touch the toolkit's display, which
            // may already be gone when the thread's locals go at exit.
            static PLASMA: RefCell<ManuallyDrop<Option<Plasma>>> = const { RefCell::new(ManuallyDrop::new(None)) };
        }

        impl Plasma {
            /// Joins the toolkit's connection the first time; None off Wayland.
            fn with<T>(window: &(impl HasDisplayHandle + ?Sized), f: impl FnOnce(&mut Plasma) -> T) -> Option<T> {
                PLASMA.with_borrow_mut(|slot| {
                    let slot: &mut Option<Plasma> = slot;
                    if slot.is_none() {
                        let RawDisplayHandle::Wayland(handle) = window.display_handle().ok()?.as_raw() else {
                            return None;
                        };
                        // SAFETY: the display belongs to the toolkit's connection,
                        // which outlives every window and this thread-local.
                        let backend = unsafe { Backend::from_foreign_display(handle.display.as_ptr().cast()) };
                        let conn = Connection::from_backend(backend);
                        let mut queue = conn.new_event_queue();
                        let mut globals = Globals::default();
                        conn.display().get_registry(&queue.handle(), ());
                        queue.roundtrip(&mut globals).ok()?;
                        *slot = Some(Plasma { conn, queue, globals, surfaces: Vec::new(), blurs: Vec::new() });
                    }
                    let plasma = slot.as_mut()?;
                    // Globals that came or went since last time.
                    let _ = plasma.queue.dispatch_pending(&mut plasma.globals);
                    Some(f(plasma))
                })
            }

            fn surface(&self, window: &(impl HasWindowHandle + ?Sized)) -> Option<WlSurface> {
                let RawWindowHandle::Wayland(handle) = window.window_handle().ok()?.as_raw() else { return None };
                // SAFETY: the toolkit keeps the surface alive while the window
                // exists, and callers only pass windows that exist.
                let id = unsafe { ObjectId::from_ptr(WlSurface::interface(), handle.surface.as_ptr().cast()) }.ok()?;
                WlSurface::from_id(&self.conn, id).ok()
            }
        }

        pub fn prepare(window: &(impl HasWindowHandle + HasDisplayHandle + ?Sized), key: u64) -> bool {
            Plasma::with(window, |plasma| {
                if plasma.surfaces.iter().any(|(known, _)| *known == key) {
                    return true;
                }
                let Some(surface) = plasma.surface(window) else { return false };
                let Some((_, shell)) = &plasma.globals.shell else { return false };
                let plasma_surface = shell.get_surface(&surface, &plasma.queue.handle(), ());
                plasma_surface.set_skip_taskbar(1);
                if shell.version() >= 5 {
                    plasma_surface.set_skip_switcher(1);
                }
                plasma.surfaces.push((key, plasma_surface));
                plasma.conn.flush().is_ok()
            })
            .unwrap_or(false)
        }

        pub fn forget(key: u64) {
            PLASMA.with_borrow_mut(|slot| {
                let Some(plasma) = slot.as_mut() else { return };
                for (_, plasma_surface) in plasma.surfaces.extract_if(.., |(known, _)| *known == key) {
                    plasma_surface.destroy();
                }
                for (_, blur) in plasma.blurs.extract_if(.., |(known, _)| *known == key) {
                    blur.release();
                }
                let _ = plasma.conn.flush();
            });
        }

        pub fn blur_behind(
            window: &(impl HasWindowHandle + HasDisplayHandle + ?Sized),
            key: u64,
            width: u32,
            height: u32,
            radius: u32,
        ) -> bool {
            Plasma::with(window, |plasma| {
                let Some(surface) = plasma.surface(window) else { return false };
                let (Some(compositor), Some((_, manager))) = (&plasma.globals.compositor, &plasma.globals.blur) else {
                    return false;
                };
                let qh = plasma.queue.handle();
                let blur = match plasma.blurs.iter().find(|(known, _)| *known == key) {
                    Some((_, blur)) => blur.clone(),
                    None => {
                        let blur = manager.create(&surface, &qh, ());
                        plasma.blurs.push((key, blur.clone()));
                        blur
                    }
                };
                let region = compositor.create_region(&qh, ());
                for strip in super::super::rounded_region(width, height, radius).chunks(4) {
                    region.add(strip[0] as i32, strip[1] as i32, strip[2] as i32, strip[3] as i32);
                }
                blur.set_region(Some(&region));
                blur.commit();
                region.destroy();
                plasma.conn.flush().is_ok()
            })
            .unwrap_or(false)
        }
    }
}

#[cfg(windows)]
mod imp {
    use std::ffi::c_void;
    use std::os::windows::ffi::OsStrExt;
    use std::path::Path;
    use std::ptr::{null, null_mut};

    use raw_window_handle::{HasDisplayHandle, HasWindowHandle, RawWindowHandle};
    use windows_sys::Win32::Foundation::{HWND, POINT};
    use windows_sys::Win32::Graphics::Dwm::{
        DWMSBT_TRANSIENTWINDOW, DWMWA_SYSTEMBACKDROP_TYPE, DWMWA_USE_IMMERSIVE_DARK_MODE, DwmExtendFrameIntoClientArea,
        DwmSetWindowAttribute,
    };
    use windows_sys::Win32::Graphics::Gdi::{
        BI_RGB, BITMAP, BITMAPINFO, BITMAPINFOHEADER, CreateCompatibleDC, CreateRoundRectRgn, DIB_RGB_COLORS, DeleteDC,
        DeleteObject, GetDC, GetDIBits, GetMonitorInfoW, GetObjectW, HBITMAP, MONITOR_DEFAULTTONEAREST, MONITORINFO,
        MonitorFromPoint, ReleaseDC, SetWindowRgn,
    };
    use windows_sys::Win32::Graphics::OpenGL::{
        ChoosePixelFormat, GL_VERSION, PFD_DOUBLEBUFFER, PFD_DRAW_TO_WINDOW, PFD_SUPPORT_OPENGL, PFD_TYPE_RGBA,
        PIXELFORMATDESCRIPTOR, SetPixelFormat, glGetString, wglCreateContext, wglDeleteContext, wglMakeCurrent,
    };
    use windows_sys::Win32::UI::Controls::MARGINS;
    use windows_sys::Win32::UI::HiDpi::{GetDpiForMonitor, MDT_EFFECTIVE_DPI};
    use windows_sys::Win32::UI::WindowsAndMessaging::{
        CreateWindowExW, DestroyIcon, DestroyWindow, GetCursorPos, GetIconInfo, HICON, ICONINFO, LR_DEFAULTCOLOR,
        PrivateExtractIconsW, WS_POPUP,
    };

    pub fn exe_icon(path: &Path, px: u32) -> Option<(u32, u32, Vec<u8>)> {
        let file: Vec<u16> = path.as_os_str().encode_wide().chain([0]).collect();
        let mut icon: HICON = null_mut();
        let mut id = 0u32;
        // SAFETY: the file name is NUL-terminated and the icon handle is
        // released after its pixels are copied out.
        unsafe {
            let got =
                PrivateExtractIconsW(file.as_ptr(), 0, px as i32, px as i32, &mut icon, &mut id, 1, LR_DEFAULTCOLOR);
            if got == 0 || got == u32::MAX || icon.is_null() {
                return None;
            }
            let pixels = icon_pixels(icon);
            DestroyIcon(icon);
            pixels
        }
    }

    unsafe fn icon_pixels(icon: HICON) -> Option<(u32, u32, Vec<u8>)> {
        // SAFETY: every GDI object made here is deleted before returning.
        unsafe {
            let mut info: ICONINFO = std::mem::zeroed();
            if GetIconInfo(icon, &mut info) == 0 {
                return None;
            }
            let pixels = (!info.hbmColor.is_null()).then(|| rgba(info.hbmColor, info.hbmMask)).flatten();
            for bitmap in [info.hbmColor, info.hbmMask] {
                if !bitmap.is_null() {
                    DeleteObject(bitmap);
                }
            }
            pixels
        }
    }

    /// The colour bitmap as RGBA. Icons without an alpha channel (older
    /// 24-bit ones) read as fully transparent, so the mask fills in alpha then.
    unsafe fn rgba(color: HBITMAP, mask: HBITMAP) -> Option<(u32, u32, Vec<u8>)> {
        // SAFETY: the buffers are sized from the bitmap's own width and height.
        unsafe {
            let mut bitmap: BITMAP = std::mem::zeroed();
            if GetObjectW(color, size_of::<BITMAP>() as i32, &mut bitmap as *mut BITMAP as *mut c_void) == 0 {
                return None;
            }
            let (width, height) = (bitmap.bmWidth, bitmap.bmHeight);
            if width <= 0 || height <= 0 {
                return None;
            }
            let dc = CreateCompatibleDC(null_mut());
            let read = |bitmap: HBITMAP| {
                let mut info: BITMAPINFO = std::mem::zeroed();
                info.bmiHeader.biSize = size_of::<BITMAPINFOHEADER>() as u32;
                info.bmiHeader.biWidth = width;
                info.bmiHeader.biHeight = -height;
                info.bmiHeader.biPlanes = 1;
                info.bmiHeader.biBitCount = 32;
                info.bmiHeader.biCompression = BI_RGB;
                let mut bgra = vec![0u8; (width * height * 4) as usize];
                let rows = GetDIBits(
                    dc,
                    bitmap,
                    0,
                    height as u32,
                    bgra.as_mut_ptr() as *mut c_void,
                    &mut info,
                    DIB_RGB_COLORS,
                );
                (rows == height).then_some(bgra)
            };
            let colour = read(color);
            let mask = if mask.is_null() { None } else { read(mask) };
            DeleteDC(dc);
            let mut bgra = colour?;
            if bgra.as_chunks::<4>().0.iter().all(|p| p[3] == 0) {
                for (index, pixel) in bgra.as_chunks_mut::<4>().0.iter_mut().enumerate() {
                    // A white mask pixel means see-through.
                    pixel[3] = match &mask {
                        Some(mask) if mask[index * 4] != 0 => 0,
                        _ => 255,
                    };
                }
            }
            for pixel in bgra.as_chunks_mut::<4>().0 {
                pixel.swap(0, 2);
            }
            Some((width as u32, height as u32, bgra))
        }
    }

    fn hwnd(window: &(impl HasWindowHandle + ?Sized)) -> Option<HWND> {
        match window.window_handle().ok()?.as_raw() {
            RawWindowHandle::Win32(handle) => Some(handle.hwnd.get() as HWND),
            _ => None,
        }
    }

    /// Makes a context on a throwaway window and reads the version, which
    /// starts with the major number ("4.6.0 NVIDIA ...", "1.1.0").
    pub fn opengl_works() -> bool {
        let class: Vec<u16> = "STATIC\0".encode_utf16().collect();
        // SAFETY: the window, device context and GL context are made, used
        // and released in order on this thread; pointers outlive the calls.
        unsafe {
            let window = CreateWindowExW(
                0,
                class.as_ptr(),
                null(),
                WS_POPUP,
                0,
                0,
                1,
                1,
                null_mut(),
                null_mut(),
                null_mut(),
                null(),
            );
            if window.is_null() {
                return false;
            }
            let dc = GetDC(window);
            let mut format: PIXELFORMATDESCRIPTOR = std::mem::zeroed();
            format.nSize = size_of::<PIXELFORMATDESCRIPTOR>() as u16;
            format.nVersion = 1;
            format.dwFlags = PFD_DRAW_TO_WINDOW | PFD_SUPPORT_OPENGL | PFD_DOUBLEBUFFER;
            format.iPixelType = PFD_TYPE_RGBA;
            format.cColorBits = 32;
            let index = ChoosePixelFormat(dc, &format);
            let mut works = false;
            if index != 0 && SetPixelFormat(dc, index, &format) != 0 {
                let context = wglCreateContext(dc);
                if !context.is_null() {
                    if wglMakeCurrent(dc, context) != 0 {
                        let version = glGetString(GL_VERSION);
                        works = !version.is_null() && (b'2'..=b'9').contains(&*version);
                        wglMakeCurrent(null_mut(), null_mut());
                    }
                    wglDeleteContext(context);
                }
            }
            ReleaseDC(window, dc);
            DestroyWindow(window);
            works
        }
    }

    pub fn cut_corners(window: &(impl HasWindowHandle + ?Sized), width: u32, height: u32, radius: u32) -> bool {
        let Some(hwnd) = hwnd(window) else { return false };
        let (width, height, round) = (width as i32, height as i32, 2 * radius as i32);
        // SAFETY: the window takes ownership of the region.
        unsafe {
            let region = CreateRoundRectRgn(0, 0, width + 1, height + 1, round, round);
            !region.is_null() && SetWindowRgn(hwnd, region, 1) != 0
        }
    }

    pub fn centre_on_pointer(width: u32, height: u32, _scale: f32) -> Option<(i32, i32)> {
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
            let (mut dpi_x, mut dpi_y) = (96u32, 96u32);
            if GetDpiForMonitor(monitor, MDT_EFFECTIVE_DPI, &mut dpi_x, &mut dpi_y) != 0 {
                dpi_x = 96;
            }
            let scale = dpi_x as f32 / 96.0;
            let (width, height) = ((width as f32 * scale) as u32, (height as f32 * scale) as u32);
            let work = info.rcWork;
            Some((
                work.left + (work.right - work.left - width as i32) / 2,
                work.top + (work.bottom - work.top - height as i32) / 2,
            ))
        }
    }

    // Taskbar and rounding are window attributes on Windows, set when the
    // window is created; focus works through winit.
    pub fn prepare(_window: &(impl HasWindowHandle + HasDisplayHandle + ?Sized), _id: u64) -> bool {
        true
    }

    pub fn forget(_id: u64) {}

    pub fn activate(_window: &(impl HasWindowHandle + ?Sized)) -> bool {
        false
    }

    /// Off until Acrylic has been checked on real Windows 11 machines; it is
    /// planned for 0.2.15. Until then the panel is plain see-through, as it
    /// was before Acrylic.
    const ACRYLIC: bool = false;

    /// Acrylic, Windows 11 22H2 and newer; older versions refuse the
    /// attribute and keep the plain see-through panel.
    pub fn blur_behind(
        window: &(impl HasWindowHandle + HasDisplayHandle + ?Sized),
        _id: u64,
        width: u32,
        height: u32,
        radius: u32,
        scale: f32,
        dark: bool,
    ) -> bool {
        if !ACRYLIC {
            return false;
        }
        let Some(hwnd) = hwnd(window) else { return false };
        let set = |attribute, value: &i32| {
            // SAFETY: `value` outlives the call, which only reads its 4 bytes.
            unsafe { DwmSetWindowAttribute(hwnd, attribute as u32, (value as *const i32).cast(), 4) == 0 }
        };
        // The blur's tint follows the window's light or dark mode.
        set(DWMWA_USE_IMMERSIVE_DARK_MODE, &i32::from(dark));
        if !set(DWMWA_SYSTEMBACKDROP_TYPE, &DWMSBT_TRANSIENTWINDOW) {
            return false;
        }
        // The backdrop shows through the whole window, client area too, and
        // fills its rectangle; the region keeps it inside the rounded panel.
        let all = MARGINS { cxLeftWidth: -1, cxRightWidth: -1, cyTopHeight: -1, cyBottomHeight: -1 };
        // SAFETY: `all` outlives the call.
        unsafe { DwmExtendFrameIntoClientArea(hwnd, &all) };
        let size = |logical: u32| (logical as f32 * scale) as u32;
        cut_corners(window, size(width), size(height), size(radius))
    }
}

#[cfg(not(any(target_os = "linux", windows)))]
mod imp {
    use raw_window_handle::{HasDisplayHandle, HasWindowHandle};

    pub fn centre_on_pointer(_width: u32, _height: u32, _scale: f32) -> Option<(i32, i32)> {
        None
    }

    pub fn opengl_works() -> bool {
        true
    }

    pub fn exe_icon(_path: &std::path::Path, _px: u32) -> Option<(u32, u32, Vec<u8>)> {
        None
    }

    pub fn cut_corners(_window: &(impl HasWindowHandle + ?Sized), _width: u32, _height: u32, _radius: u32) -> bool {
        false
    }

    pub fn prepare(_window: &(impl HasWindowHandle + HasDisplayHandle + ?Sized), _id: u64) -> bool {
        false
    }

    pub fn forget(_id: u64) {}

    pub fn activate(_window: &(impl HasWindowHandle + ?Sized)) -> bool {
        false
    }

    pub fn blur_behind(
        _window: &(impl HasWindowHandle + HasDisplayHandle + ?Sized),
        _id: u64,
        _width: u32,
        _height: u32,
        _radius: u32,
        _scale: f32,
        _dark: bool,
    ) -> bool {
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

    #[test]
    fn exe_icons_come_out_as_rgba_on_windows_only() {
        let missing = std::path::Path::new("/nonexistent/program.exe");
        assert_eq!(super::exe_icon(missing, 48), None);
        if cfg!(windows) {
            let root = std::env::var("SystemRoot").unwrap_or_else(|_| r"C:\windows".into());
            let notepad = std::path::PathBuf::from(root).join(r"system32\notepad.exe");
            let (width, height, rgba) = super::exe_icon(&notepad, 48).expect("notepad has an icon");
            assert_eq!((width, height), (48, 48));
            assert_eq!(rgba.len(), 48 * 48 * 4);
            assert!(rgba.as_chunks::<4>().0.iter().any(|p| p[3] == 255), "some pixel is opaque");
        }
    }
}
