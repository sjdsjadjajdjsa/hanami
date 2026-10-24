//! Game pictures for the rows: files are read and shrunk on a worker thread,
//! the main thread only hands out finished pictures. Nothing here blocks
//! opening the panel.

use std::cell::{Cell, OnceCell, RefCell};
use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};
use std::sync::mpsc::{Receiver, Sender, channel};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use image::imageops::FilterType;
use image::{DynamicImage, ImageReader, RgbaImage};
use slint::{Image, Rgba8Pixel, SharedPixelBuffer};

/// Decoded pictures kept at once: 600 at 24 px is about 1.4 MB, at 48 px 5.5 MB.
const KEEP: usize = 600;
/// How big a row's picture is drawn, in logical pixels.
pub const ROW_PX: f32 = 24.0;
/// Pictures are never kept bigger than this, whatever the scale.
const MOST_PX: u32 = 96;
/// Larger files are not read: an icon is never that big.
const MAX_BYTES: u64 = 32 * 1024 * 1024;
/// How often `ready` is called while a long queue is being decoded.
const TELL: Duration = Duration::from_millis(50);

type Pixels = SharedPixelBuffer<Rgba8Pixel>;
type Done = Arc<Mutex<Vec<(PathBuf, u32, Option<Pixels>)>>>;

enum Slot {
    Loading,
    Ready(Option<Image>),
}

pub struct Icons {
    px: Cell<u32>,
    ready: Arc<dyn Fn() + Send + Sync>,
    cache: RefCell<HashMap<PathBuf, (Slot, u64)>>,
    /// Paths that can't be read, kept apart so evicting never retries them.
    failed: RefCell<HashSet<PathBuf>>,
    uses: RefCell<u64>,
    done: Done,
    worker: OnceCell<Sender<(PathBuf, u32)>>,
}

/// The size in pixels a row's picture takes on a screen at `scale`, so it is
/// kept exactly as big as it is drawn: 24 at 100 %, 36 at 150 %, 48 at 200 %.
pub fn row_px(scale: f32) -> u32 {
    // The small nudge keeps float noise (36.000004) from rounding up a pixel.
    ((ROW_PX * scale.max(1.0) - 0.01).ceil() as u32).min(MOST_PX)
}

impl Icons {
    /// Pictures `px` x `px` big; `ready` is called (from the worker thread)
    /// when newly decoded pictures can be fetched with `get`.
    pub fn new(px: u32, ready: impl Fn() + Send + Sync + 'static) -> Self {
        Self {
            px: Cell::new(px),
            ready: Arc::new(ready),
            cache: RefCell::default(),
            failed: RefCell::default(),
            uses: RefCell::new(0),
            done: Arc::default(),
            worker: OnceCell::new(),
        }
    }

    /// The picture for `path`, or None while it is still loading or when it
    /// can't be read. The first ask starts decoding on a worker thread.
    pub fn get(&self, path: &Path) -> Option<Image> {
        self.take_done();
        if self.failed.borrow().contains(path) {
            return None;
        }
        let mut cache = self.cache.borrow_mut();
        let mut uses = self.uses.borrow_mut();
        *uses += 1;
        if let Some((slot, used)) = cache.get_mut(path) {
            *used = *uses;
            return match slot {
                Slot::Ready(image) => image.clone(),
                Slot::Loading => None,
            };
        }
        if cache.len() >= KEEP {
            evict(&mut cache);
        }
        cache.insert(path.to_path_buf(), (Slot::Loading, *uses));
        let _ = self.worker().send((path.to_path_buf(), self.px.get()));
        None
    }

    /// The size pictures are made at now.
    pub fn px(&self) -> u32 {
        self.px.get()
    }

    /// Makes pictures `px` x `px` from now on. The ones made at another size
    /// are dropped and made again when asked for. True when the size changed.
    pub fn set_px(&self, px: u32) -> bool {
        if px == self.px.get() {
            return false;
        }
        self.px.set(px);
        self.cache.borrow_mut().clear();
        true
    }

    /// The picture for `path` if it is decoded already; never starts loading.
    pub fn peek(&self, path: &Path) -> Option<Image> {
        self.take_done();
        match self.cache.borrow().get(path) {
            Some((Slot::Ready(image), _)) => image.clone(),
            _ => None,
        }
    }

    fn worker(&self) -> &Sender<(PathBuf, u32)> {
        self.worker.get_or_init(|| {
            let (sender, receiver) = channel();
            let (done, ready) = (self.done.clone(), self.ready.clone());
            std::thread::Builder::new()
                .name("icons".into())
                .spawn(move || work(receiver, done, ready))
                .expect("thread");
            sender
        })
    }

    fn take_done(&self) {
        let done = std::mem::take(&mut *self.done.lock().unwrap_or_else(|e| e.into_inner()));
        if done.is_empty() {
            return;
        }
        let mut cache = self.cache.borrow_mut();
        for (path, px, pixels) in done {
            let Some(pixels) = pixels else {
                cache.remove(&path);
                self.failed.borrow_mut().insert(path);
                continue;
            };
            // Asked for before the scale changed; the new size is on its way.
            if px != self.px.get() {
                continue;
            }
            if let Some((slot, _)) = cache.get_mut(&path) {
                *slot = Slot::Ready(Some(Image::from_rgba8(pixels)));
            }
        }
    }
}

/// Drops the least recently asked-for quarter of the cache. A picture still
/// loading is dropped too; its result is ignored and it is asked for again.
fn evict(cache: &mut HashMap<PathBuf, (Slot, u64)>) {
    let mut ages: Vec<u64> = cache.values().map(|(_, used)| *used).collect();
    ages.sort_unstable();
    let cutoff = ages[ages.len() / 4];
    cache.retain(|_, (_, used)| *used > cutoff);
}

/// Decodes everything queued, saying so every `TELL` and at the end.
fn work(receiver: Receiver<(PathBuf, u32)>, done: Done, ready: Arc<dyn Fn() + Send + Sync>) {
    while let Ok(first) = receiver.recv() {
        let mut told = Instant::now();
        let mut pending = false;
        let mut queue = vec![first];
        loop {
            for (path, px) in queue.drain(..) {
                let pixels = decode(&path, px);
                done.lock().unwrap_or_else(|e| e.into_inner()).push((path, px, pixels));
                pending = true;
                if told.elapsed() >= TELL {
                    ready();
                    (told, pending) = (Instant::now(), false);
                }
            }
            queue.extend(receiver.try_iter());
            if queue.is_empty() {
                break;
            }
        }
        if pending {
            ready();
        }
        desktop::return_memory();
    }
}

/// `path` as a picture that fits in `px` x `px`, keeping its shape.
pub fn decode(path: &Path, px: u32) -> Option<Pixels> {
    let image = load(path, px)?;
    let (width, height) = (image.width(), image.height());
    let fitted = if width > px || height > px {
        image.resize(px, px, FilterType::Lanczos3)
    } else if width < px && height < px {
        image.resize(px, px, FilterType::CatmullRom)
    } else {
        image
    };
    let rgba = fitted.into_rgba8();
    Some(SharedPixelBuffer::clone_from_slice(rgba.as_raw(), rgba.width(), rgba.height()))
}

fn load(path: &Path, px: u32) -> Option<DynamicImage> {
    // Heroic's cached art has no extension; the bytes say what it is.
    let extension = path.extension().and_then(|ext| ext.to_str()).map(str::to_ascii_lowercase).unwrap_or_default();
    if extension == "exe" || extension == "dll" {
        let (width, height, rgba) = desktop::exe_icon(path, px)?;
        return RgbaImage::from_raw(width, height, rgba).map(DynamicImage::ImageRgba8);
    }
    if std::fs::metadata(path).ok()?.len() > MAX_BYTES {
        return None;
    }
    let data = std::fs::read(path).ok()?;
    if extension == "svg" || extension == "svgz" {
        return svg_image(&data, px);
    }
    let mut reader = ImageReader::new(std::io::Cursor::new(data)).with_guessed_format().ok()?;
    let mut limits = image::Limits::default();
    limits.max_image_width = Some(4096);
    limits.max_image_height = Some(4096);
    limits.max_alloc = Some(64 << 20);
    reader.limits(limits);
    reader.decode().ok()
}

/// A picture already in memory, for the sample games `hanami --snapshot` draws.
pub fn from_bytes(data: &[u8], px: u32) -> Option<Pixels> {
    let image = image::load_from_memory(data).ok()?;
    let rgba = image.resize(px, px, FilterType::Lanczos3).into_rgba8();
    Some(SharedPixelBuffer::clone_from_slice(rgba.as_raw(), rgba.width(), rgba.height()))
}

/// An SVG drawn to fit `px` pixels, as straight RGBA.
pub fn svg(data: &[u8], px: u32) -> Option<Pixels> {
    let rgba = svg_image(data, px)?.into_rgba8();
    Some(SharedPixelBuffer::clone_from_slice(rgba.as_raw(), rgba.width(), rgba.height()))
}

fn svg_image(data: &[u8], px: u32) -> Option<DynamicImage> {
    use resvg::tiny_skia::{Pixmap, Transform};
    let tree = resvg::usvg::Tree::from_data(data, &resvg::usvg::Options::default()).ok()?;
    let size = tree.size();
    let scale = (px as f32 / size.width()).min(px as f32 / size.height());
    let (width, height) =
        ((size.width() * scale).round().max(1.0) as u32, (size.height() * scale).round().max(1.0) as u32);
    let mut pixmap = Pixmap::new(width, height)?;
    resvg::render(&tree, Transform::from_scale(scale, scale), &mut pixmap.as_mut());
    let rgba: Vec<u8> = pixmap
        .pixels()
        .iter()
        .flat_map(|p| {
            let c = p.demultiply();
            [c.red(), c.green(), c.blue(), c.alpha()]
        })
        .collect();
    RgbaImage::from_raw(width, height, rgba).map(DynamicImage::ImageRgba8)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::mpsc;
    use std::time::Duration;

    fn dir() -> PathBuf {
        let dir =
            std::env::temp_dir().join(format!("hanami-icons-{}-{:?}", std::process::id(), std::thread::current().id()));
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    fn png(path: &Path, width: u32, height: u32) {
        let file = std::fs::File::create(path).unwrap();
        let mut encoder = png::Encoder::new(file, width, height);
        encoder.set_color(png::ColorType::Rgba);
        encoder.set_depth(png::BitDepth::Eight);
        let pixels: Vec<u8> = (0..width * height).flat_map(|_| [200, 100, 50, 255]).collect();
        encoder.write_header().unwrap().write_image_data(&pixels).unwrap();
    }

    #[test]
    fn pictures_fit_the_square_and_keep_their_shape() {
        let dir = dir();
        let wide = dir.join("wide.png");
        png(&wide, 200, 100);
        let pixels = decode(&wide, 48).unwrap();
        assert_eq!((pixels.width(), pixels.height()), (48, 24));
        assert_eq!(pixels.as_slice()[0], Rgba8Pixel { r: 200, g: 100, b: 50, a: 255 });

        let small = dir.join("small.png");
        png(&small, 16, 16);
        let pixels = decode(&small, 48).unwrap();
        assert_eq!((pixels.width(), pixels.height()), (48, 48));

        let svg = dir.join("tall.svg");
        let shape = r##"<svg xmlns="http://www.w3.org/2000/svg" width="10" height="20"><rect width="10" height="20" fill="#f00"/></svg>"##;
        std::fs::write(&svg, shape).unwrap();
        let pixels = decode(&svg, 48).unwrap();
        assert_eq!((pixels.width(), pixels.height()), (24, 48));
        assert_eq!(pixels.as_slice()[0], Rgba8Pixel { r: 255, g: 0, b: 0, a: 255 });

        std::fs::write(dir.join("broken.png"), "not a picture").unwrap();
        assert!(decode(&dir.join("broken.png"), 48).is_none());
        assert!(decode(&dir.join("missing.jpg"), 48).is_none());
        assert!(decode(&dir.join("noext"), 48).is_none());
        if cfg!(windows) {
            let root = std::env::var("SystemRoot").unwrap_or_else(|_| r"C:\windows".into());
            let notepad = decode(&PathBuf::from(root).join(r"system32\notepad.exe"), 48).expect("exe icon");
            assert_eq!((notepad.width(), notepad.height()), (48, 48));
        }
        std::fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn get_loads_in_the_background_and_remembers_failures() {
        let dir = dir();
        let good = dir.join("good.png");
        png(&good, 64, 64);
        let bad = dir.join("bad.png");
        std::fs::write(&bad, "x").unwrap();

        let (sender, ready) = mpsc::channel();
        let icons = Icons::new(48, move || {
            let _ = sender.send(());
        });
        assert!(icons.get(&good).is_none());
        assert!(icons.get(&bad).is_none());
        let deadline = Instant::now() + Duration::from_secs(10);
        let image = loop {
            ready.recv_timeout(deadline.saturating_duration_since(Instant::now())).expect("ready is called");
            icons.take_done();
            let both = icons.cache.borrow().values().all(|(slot, _)| matches!(slot, Slot::Ready(_)));
            if both {
                break icons.get(&good).expect("decoded");
            }
        };
        assert_eq!((image.size().width, image.size().height), (48, 48));
        assert!(icons.get(&bad).is_none());
        assert_eq!(icons.cache.borrow().len(), 1);
        assert!(icons.failed.borrow().contains(&bad));
        assert!(icons.peek(&good).is_some() && icons.peek(&bad).is_none());
        std::fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn pictures_are_kept_as_big_as_the_row_draws_them() {
        assert_eq!(row_px(1.0), 24);
        assert_eq!(row_px(1.25), 30);
        assert_eq!(row_px(1.5), 36);
        assert_eq!(row_px(2.0), 48);
        assert_eq!(row_px(0.5), 24);
        assert_eq!(row_px(10.0), MOST_PX);

        let dir = dir();
        let lutris = dir.join("lutris.png");
        png(&lutris, 128, 128);
        for scale in [1.0, 1.5, 2.0] {
            let pixels = decode(&lutris, row_px(scale)).unwrap();
            assert_eq!((pixels.width(), pixels.height()), (row_px(scale), row_px(scale)));
        }

        // A new scale drops the pictures made at the old size.
        let icons = Icons::new(row_px(2.0), || {});
        icons.cache.borrow_mut().insert(lutris.clone(), (Slot::Ready(None), 0));
        assert!(!icons.set_px(48));
        assert!(icons.set_px(row_px(1.5)));
        assert_eq!(icons.px(), 36);
        assert!(icons.cache.borrow().is_empty());
        // One that was asked for at the old size is not kept when it lands.
        icons.cache.borrow_mut().insert(lutris.clone(), (Slot::Loading, 0));
        icons.done.lock().unwrap().push((lutris.clone(), 48, decode(&lutris, 48)));
        icons.take_done();
        assert!(icons.peek(&lutris).is_none());
        icons.done.lock().unwrap().push((lutris.clone(), 36, decode(&lutris, 36)));
        assert_eq!(icons.peek(&lutris).map(|image| image.size().width), Some(36));
        std::fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn the_cache_stays_bounded() {
        let icons = Icons::new(48, || {});
        for i in 0..(KEEP * 2) {
            icons.get(&PathBuf::from(format!("/nonexistent/{i}.png")));
        }
        assert!(icons.cache.borrow().len() <= KEEP);
        let mut cache = HashMap::new();
        for i in 0..KEEP as u64 {
            cache.insert(PathBuf::from(format!("{i}")), (Slot::Ready(None), i));
        }
        evict(&mut cache);
        assert!(cache.len() <= KEEP * 3 / 4 + 1);
        assert!(cache.contains_key(Path::new(&(KEEP as u64 - 1).to_string())));
    }
}
