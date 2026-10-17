# Node lessons (`node`, TypeScript)

## Layout

```
<module dir>/                       # npm workspace: one node_modules and package-lock.json
├── package.json                    # generated: workspaces + pinned dev tools (tsx, typescript, vitest, biome)
├── tsconfig.base.json              # generated: strict, nodenext, noEmit, .ts imports allowed
└── <lesson dir>/
    ├── package.json                # name <project>, "type": "module", its pinned dependencies
    ├── tsconfig.json               # extends ../tsconfig.base.json
    ├── src/
    │   ├── main.ts                 # the live run: `npx tsx src/main.ts`
    │   └── *.ts                    # the lesson code
    └── tests/*.test.ts             # offline tests (vitest)
```

- ES modules only. Import local files **with the `.ts` extension**: `import { route } from "./router.ts";`. tsx runs them, and `tsc` allows it.
- `verbatimModuleSyntax` is on: import types with `import type { … }`.

## Dependencies

- Add runtime dependencies to the lesson's `package.json` `dependencies`, **pinned exactly** (`"zod": "4.1.12"`, no `^`). Then run `npm install --no-audit --no-fund` in the **module** directory. All lessons of a module share one lockfile, so keep versions consistent.
- Don't add dev tools: they come from the module's `package.json`. For extra type packages (`@types/…`), add them to the lesson's `devDependencies`, pinned.

## Installed sources

`<module dir>/node_modules/<package>/`: the `package.json` `exports` and `types` fields point to the type declarations (`*.d.ts`). Read those for signatures.

## Style

- TSDoc comments (`/** … */`) on every exported function and type.
- Environment: `process.env.NAME`. Check required variables at startup and fail with a clear message.
- Format and lint in the lesson directory: `npx biome format --write src tests`, `npx biome lint --write src tests`, then `npx tsc -p tsconfig.json` (type check). The course's `biome.json` sets 2-space indentation and double quotes.

## Tests and run

- Tests: `tests/*.test.ts` with vitest (`import { expect, test } from "vitest";`). Verify runs `npx vitest run`.
- Live run: `run_cmd` is usually `npx tsx src/main.ts`, run in the lesson directory.
