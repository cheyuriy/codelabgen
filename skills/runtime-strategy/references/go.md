# Go (`go`)

What `codelabgen scaffold` creates:

```
<course>/
└── <n>-<module-slug>/
    ├── go.work                     # `use` lists every lesson of the module
    └── <id>-<lesson-slug>/         # one Go module per lesson: codelab.local/l<id>_<slug>
        ├── go.mod / go.sum
        ├── main.go                 # package main, the live run (go run .)
        ├── *.go
        └── *_test.go               # go test
```

Consequences for planning:
- **Each lesson is its own Go module**, so lessons may even use different versions, but keep them consistent within a module for clarity.
- **The `go` directive** follows the user's installed toolchain (`go env GOVERSION`).
- **Live runs are `go run .`**: servers must stop on their own for verification (a lesson can start a server, make a few requests against it, print the results and shut down).
- **Offline tests** with the standard `testing` package; `net/http/httptest` for HTTP handlers; fakes for external services.
