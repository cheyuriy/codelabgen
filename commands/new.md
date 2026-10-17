---
description: Create a codelabgen course from start to finish in one session — research, source review, curriculum, plan review, lessons, assembly and evaluation, with all questions asked in the chat
argument-hint: "<topic> --target <dir> [--lang ru] [--version <v>] [--source <url> …] [--source-type <type> …] [--sources-per-type N] [--wishes \"…\"]"
---

Create a new codelabgen course. Arguments: `$ARGUMENTS`

Load the `codelabgen-orchestrator` skill and run its main loop from phase `init` **to the end**: research, the source review, topics and curriculum, the plan review, scaffold, every lesson, assembly, then the evaluation. Ask every question in the session with AskUserQuestion; never stop to have the user run another command or edit a file (except putting secrets into `.env`).

- `<topic>` is the technology, for example `LangGraph` or `"Go generics"`.
- `--target <dir>` is required: the course directory, outside the plugin. Ask for it if it is missing; never pick one yourself.
- `--lang` is the course language (default `en`). `--version` pins the technology version (default: the latest stable release, which tech-scout finds and you confirm with a question).
- `--source <url>` (repeatable): sources the user wants included. They are recorded first and kept.
- `--source-type <type>` (repeatable): search only these source types (`official-docs`, `official-blog`, `package-internals`, `article`, `github-repo`, `qa`, `paper-spec`, `talk-workshop`, `university`, `book-course`). The default is all of them.
- `--sources-per-type N`: at most N sources per type (default 8).
- `--wishes "…"`: the user's wishes for the course, such as scope, depth or size ("at most 3 lessons"). They are saved in the config and given to the curriculum architect.

Pass all of these on to `codelabgen init`; the options have the same names.
