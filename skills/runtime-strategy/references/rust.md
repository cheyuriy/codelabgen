# Rust (`rust`)

What `codelabgen scaffold` creates:

```
<course>/
└── <n>-<module-slug>/
    ├── Cargo.toml                  # virtual workspace: `members` lists every lesson of the module
    ├── Cargo.lock                  # one lockfile and one target/ for the module
    └── <id>-<lesson-slug>/         # one package per lesson: l<id>-<slug>, crate l<id>_<slug>
        ├── Cargo.toml
        ├── src/lib.rs              # the lesson code
        ├── src/main.rs             # the live run (cargo run --quiet)
        └── tests/*.rs              # integration tests (cargo test)
```

Consequences for planning:
- **One Cargo workspace per module**: its lessons share one lockfile, so they use the same crate versions, and one `target/`, so a crate compiles once per module rather than once per lesson.
- **The edition** follows the user's installed toolchain: 2024 with Rust 1.85 or later, else 2021.
- **The user needs a C linker** (`cc`, from `build-essential` or Xcode tools) as well as `cargo`, `clippy` and `rustfmt`. `rustup` installs the last three by default. Crates with build scripts or C code (`ring`, `openssl-sys`, `rusqlite` with `bundled`) need the C toolchain, and the first build takes longer. Prefer pure-Rust crates when there is a choice (`rustls` over `native-tls`).
- **First builds are slow**: compiling a big dependency tree (tokio, axum, sqlx) takes minutes. Keep a module's lessons on the same crate versions, so the shared `target/` is reused.
- **Live runs are `cargo run --quiet`**: servers must stop on their own for verification (a lesson can start a server on a background task, make a few requests against it, print the results and shut down).
- **Offline tests** with the built-in test harness; `#[tokio::test]` for async code; fakes behind a trait for external services.
