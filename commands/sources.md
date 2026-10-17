---
description: Review the sources of a codelabgen course — apply the user's edits, pass the source gate, then continue the course to the end
argument-hint: "[--course <dir>]"
---

Continue the source review of a codelabgen course. Arguments: `$ARGUMENTS`

Load the `codelabgen-orchestrator` skill and follow its `gate_sources` phase.

- `--course <dir>` selects the course; otherwise use `$CODELABGEN_COURSE` or the current directory.
- If the course is not at `gate_sources`, say which phase it is in and what the right next command is.
- Changes the user describes in this message (for example "drop the Medium articles, add https://…") are source decisions: record them with `codelabgen sources decide` / `sources add`. If they edited `.codelabgen/sources.md` by hand instead, run `codelabgen sources apply`.
- Advance past the gate (`codelabgen state phase topics --approved`) only after the user explicitly approves the list. Then continue the main loop to the end, asking the plan review in the session too.
