---
description: Show progress of a codelabgen course — phase, lesson stages, blocked lessons
argument-hint: "[course-dir]"
allowed-tools: Bash(codelabgen:*), Bash(uv run:*)
---

Show the status of the codelabgen course at `$ARGUMENTS` (or the current directory when no argument is given).

1. Run `codelabgen state show --course <dir>`, dropping `--course` when no directory was given. If `codelabgen` is not on `PATH`, use `uv run --project ${CLAUDE_PLUGIN_ROOT} codelabgen` instead.
2. Run `codelabgen state next --course <dir>`.
3. Reply with a compact summary:
   - the course topic and current phase
   - counts per lesson stage
   - blocked lessons with their reasons, and stale lessons
   - what happens next, from `state next`

If the CLI reports that no course was found, say so and suggest `/codelabgen:new`. Do not change any state.
