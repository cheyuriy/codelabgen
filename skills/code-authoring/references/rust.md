# Rust lessons (`rust`)

## Layout

```
<module dir>/                       # Cargo workspace: one Cargo.lock and one target/
├── Cargo.toml                      # generated: `members` lists every lesson of the module
└── <lesson dir>/
    ├── Cargo.toml                  # package <project> (l1-2-routing), its pinned dependencies
    ├── src/
    │   ├── lib.rs                  # the lesson code: crate <package> (l1_2_routing)
    │   ├── *.rs                    # more modules, declared in lib.rs (`pub mod router;`)
    │   └── main.rs                 # the live run, `cargo run --quiet`: uses the library
    └── tests/*.rs                  # offline tests (integration tests)
```

- Put the code in `src/lib.rs` and its modules, and keep `main.rs` short: it imports the library by crate name, `use l1_2_routing::router;`. Integration tests in `tests/` import it the same way.
- The scaffold's placeholder is `src/main.rs` with an empty `main`. A lesson with nothing to put in a library may keep everything in `main.rs` and test it with a `#[cfg(test)] mod tests` at the bottom of the file.

## Dependencies

- In the lesson directory: `cargo add <crate>@=<exact version>` (for example `cargo add base64@=0.23.1`, or `cargo add tokio@=1.47.1 --features rt-multi-thread,macros`). The `=` pins it exactly. Then run `cargo fetch` in the **module** directory: it updates the shared `Cargo.lock` and downloads the sources. All lessons of a module share the lockfile, so keep versions consistent.
- Enable only the features the lesson uses, and say why in a comment next to the dependency when it isn't obvious.
- Dev-only crates (for example `tokio` with `test-util`) go in with `cargo add --dev`.

## Installed sources

After `cargo fetch`: `${CARGO_HOME:-~/.cargo}/registry/src/*/<crate>-<version>/`. Grep `src/lib.rs` for `pub use` and `pub mod` to find what is exported and from where. `cargo doc -p <crate> --no-deps` builds the docs locally when the source is hard to follow.

## Style

- `//!` at the top of `lib.rs` says what the lesson's code does; `///` doc comments on every public item.
- Errors are returned (`Result`) and handled, not `unwrap()`ped, in the library code. `main` may use `expect("why this can't fail")` for setup, with a message that explains it.
- Prefer owned, simple types (`String`, `Vec<u8>`) over lifetimes and generics unless the lesson is about them.
- Environment: `std::env::var("NAME")`. Check required ones at startup.
- Format: `cargo fmt`. Lint: `cargo clippy --all-targets -- -D warnings`. Verify fails on any clippy warning or unformatted file, so run both before you finish.

## Tests and run

- Tests: `#[test]` functions in `tests/*.rs`, or in a `#[cfg(test)] mod tests` next to the code. Doc examples in `///` comments run as tests too, so keep them correct or mark them `no_run`. Verify runs `cargo test --locked`.
- Live run: `run_cmd` is usually `cargo run --quiet`, in the lesson directory. Arguments go after `--`: `cargo run --quiet -- --stream`. `--quiet` hides the compiler's progress lines, so recordings and the notes show only the program's output.
