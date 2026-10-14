# softbuffer 0.4.8, patched

Copied from crates.io, one change: `src/backends/wayland/buffer.rs` makes
`Argb8888` buffers instead of `Xrgb8888`, so the panel is see-through on
Wayland the way it is on X11 and Windows. Slint's software renderer writes
premultiplied alpha, which is what Wayland expects.

Upstream is adding an `AlphaMode` setting (see CHANGELOG.md, unreleased);
drop this copy and the `[patch.crates-io]` line in the root Cargo.toml once a
softbuffer with it ships and Slint uses it.
