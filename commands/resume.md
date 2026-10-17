---
description: Continue a codelabgen course from wherever it stopped — including work interrupted mid-task in an earlier session
argument-hint: "[course-dir]"
---

Resume the codelabgen course at `$ARGUMENTS` (or `$CODELABGEN_COURSE`, or the current directory).

Load the `codelabgen-orchestrator` skill and run its main loop:

1. `codelabgen state show` and `codelabgen state next`. Tell the user in two or three lines where the course is and what comes next. If `state next` lists `interrupted` tasks, say which work was cut off.
2. Continue with the actions `state next` gives, restarting interrupted tasks with the instruction to complete their partial work.
3. Stop at every review gate and whenever the user is needed, exactly as in a fresh run. A resumed run never skips a gate.
