---
description: Assemble a codelabgen course — glossary, READMEs and table of contents, run.sh, checks, the MkDocs site, and a git commit
argument-hint: "[--course <dir>] [--no-commit]"
---

Assemble the codelabgen course. Arguments: `$ARGUMENTS`

Load the `codelabgen-orchestrator` and `site-assembly` skills and follow the assembly procedure.

- `--course <dir>` selects the course; otherwise use `$CODELABGEN_COURSE` or the current directory.
- `--no-commit` stops after the site build.
- If some lessons are not `done`, you may still generate and check (steps 2–4) to preview the course, but don't advance the phase or commit. Say which lessons are unfinished.
