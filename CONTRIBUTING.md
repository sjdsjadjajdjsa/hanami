# Contributing

Thanks for wanting to help. Small fixes, new ports and bug reports are all
welcome.

## Adding a port

This is the easiest way to help, and it needs no Rust. Add an entry to
[ports.toml](ports.toml) and open a pull request. [docs/PORTS.md](docs/PORTS.md)
has the steps. Say where the file names come from, so they can be checked.

## Reporting a bug

Use **Report a problem** in the tray menu. It opens an issue with your
version and system filled in. Nothing is sent until you press Submit.

For a security problem, see [SECURITY.md](SECURITY.md) and don't open a public
issue.

## Changing the code

Build it as described in the [README](README.md#build-from-source). Before you
open a pull request, run what CI runs:

```
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
cargo fmt --all
```

A few things to keep in mind:

- Hanami is meant to be light. If a change adds a wake-up, a thread or a
  dependency, say why. [docs/benchmarks.md](docs/benchmarks.md) explains how
  to measure the cost with `tools/bench.py`.
- The look comes from the tokens in `hanami/ui/hanami.slint`. Follow
  [docs/DESIGN.md](docs/DESIGN.md) and add to it first if a screen needs
  something new.
- [docs/SPEC.md](docs/SPEC.md) says what Hanami does and what it leaves out.
  [docs/ROADMAP.md](docs/ROADMAP.md) says what comes next. For a larger
  change, open an issue first so we can agree on it.
- Keep pull requests small and about one thing. A few plain lines saying
  what changed for the person using it is enough.

By contributing, you agree your work is released under the
[GPL, version 3 or later](LICENSE), like the rest of Hanami.
