# Node with TypeScript (`node`)

What `codelabgen scaffold` creates:

```
<course>/
├── biome.json                      # format and lint rules for all lessons
└── <n>-<module-slug>/              # one npm workspace per module
    ├── package.json                # workspaces + pinned dev tools: typescript, tsx, vitest, @biomejs/biome, @types/node
    ├── tsconfig.base.json          # strict, nodenext, noEmit, .ts imports allowed
    ├── package-lock.json           # one lock for the module
    └── <id>-<lesson-slug>/         # a workspace member
        ├── package.json            # name l<id>-<slug>, "type": "module", its pinned dependencies
        ├── tsconfig.json           # extends ../tsconfig.base.json
        ├── src/main.ts             # the live run (npx tsx src/main.ts)
        └── tests/*.test.ts         # vitest
```

Consequences for planning:
- **TypeScript is the default**, also for JavaScript libraries; it costs learners nothing with tsx and catches mistakes. Plain JavaScript lessons are fine where the course is explicitly about JS.
- **One version per module:** lessons share one lockfile.
- **Node version:** the user's installed Node (24 LTS or later recommended). Lessons must not need native build tools.
- **Offline tests** with vitest, using fakes or in-memory implementations for LLMs and services.
- **Browser-only libraries** (React components, DOM APIs) aren't covered by this runtime yet: report `needs-user`.
