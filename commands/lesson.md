---
description: Produce lessons of a codelabgen course — one lesson, or all remaining ones — through spec, code, verify, read-along, notes and review
argument-hint: "[lesson-id | all] [--course <dir>] [--redo <stage>]"
---

Produce lessons of a codelabgen course. Arguments: `$ARGUMENTS`

Load the `codelabgen-orchestrator` skill and follow its lesson-production section.

- With a lesson id, work on that lesson only, until it is `done`, blocked or needs the user. If an earlier lesson of the same module is not done yet, say so and stop.
- With `all` or no id, keep taking work from `codelabgen state next` until no lesson is left or every remaining one is blocked.
- With `--redo <stage>`, first move the lesson back with `codelabgen state set <id> <stage> --note "redo requested by the user"`, then continue from there. For example, `--redo verified` rewrites the read-along and notes.
- `--course <dir>` selects the course; otherwise use `$CODELABGEN_COURSE` or the current directory.

If the course is not in the `lessons` phase yet, explain which phase it is in and stop. For an M1 test course you prepare by hand, advance the phases with `codelabgen state phase` (gates need `--approved`) only when the user asks you to.
