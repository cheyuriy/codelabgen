---
description: Review the plan of a codelabgen course — curriculum, example storyline, services, external services and keys — then build the rest of the course
argument-hint: "[--course <dir>] [feedback or answers]"
---

Continue the plan review of a codelabgen course. Arguments: `$ARGUMENTS`

Load the `codelabgen-orchestrator` skill and follow its `gate_plan` phase (questions in the session), then continue the main loop to the end.

- `--course <dir>` selects the course; otherwise use `$CODELABGEN_COURSE` or the current directory.
- If the course is still in `topics` or `curriculum`, finish those phases first. If it is earlier, say which phase it is in and which command comes next.
- Text after the options is the user's feedback on the plan or their answers to the open questions. Handle it as one feedback round.
- Advance past the gate only after the user explicitly approves the plan and every question is answered.
