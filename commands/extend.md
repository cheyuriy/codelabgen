---
description: Extend a finished codelabgen course — deepen a topic or add new ones — with gap analysis, targeted research, a reviewed curriculum change, new lessons and a rebuild
argument-hint: "<course-dir> \"<request>\""
---

Extend a codelabgen course. Arguments: `$ARGUMENTS`

The first argument is the course directory. The rest is the user's request, for example "add a lesson on streaming" or "go deeper on checkpointers in 1.3".

Load the `codelabgen-orchestrator` skill and follow its **Extensions** section, using the main loop (`codelabgen state next`).

- If an extension is already in progress, continue it instead of starting a new one, and say so.
- Stop at the extension's review gate. Apply the change only after the user approves it, and renumber existing lessons only with their explicit consent.
