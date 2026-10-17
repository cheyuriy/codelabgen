# Go lessons (`go`)

## Layout

```
<module dir>/
├── go.work                         # generated: `use` lists every lesson of the module
└── <lesson dir>/                   # one Go module per lesson
    ├── go.mod                      # module codelab.local/<package>
    ├── go.sum
    ├── main.go                     # package main: the live run, `go run .`
    ├── *.go                        # the lesson code (package main, or subpackages in folders)
    └── *_test.go                   # offline tests next to the code they test
```

- Subpackages import by module path: `import "codelab.local/l1_2_routing/queue"`.
- The `tests/` folder the scaffold creates is unused in Go; tests live next to the code, as Go expects.

## Dependencies

- In the lesson directory: `go get <module>@<exact version>` (for example `go get github.com/go-chi/chi/v5@v5.2.3`), then `go mod tidy`. Each lesson has its own `go.mod`, but keep versions consistent across a module's lessons.

## Installed sources

`$(go env GOMODCACHE)/<module path>@<version>/`. Use `go doc <package>.<Symbol>` for quick signatures.

## Style

- Doc comments on every exported identifier, starting with its name (`// Route picks …`).
- Errors returned and checked, not panics, except in `main` for setup failures.
- Environment: `os.Getenv("NAME")`. Check required ones at startup.
- Format: `gofmt -w .`. Vet: `go vet ./...`. Verify fails if `gofmt -l .` lists any file.

## Tests and run

- Tests: `*_test.go` with the standard `testing` package. Table-driven tests are welcome when they stay short. Verify runs `go test ./...`.
- Live run: `run_cmd` is usually `go run .`, in the lesson directory.
