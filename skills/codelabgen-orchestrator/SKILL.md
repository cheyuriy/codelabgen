---
name: codelabgen-orchestrator
description: Runs the codelabgen pipeline from the main session — dispatches the worker agents, records state through the `codelabgen` CLI, handles verify failures, reviews and rework, and stops for the user at gates. Load when a /codelabgen command asks for it.
user-invocable: false
---

# codelabgen orchestrator

You drive course generation from the main session. Only you start subagents, and only you change course state (see the state-protocol skill). Workers do one job each and end with a status JSON.

> This version covers **research** (phases `init` to `gate_sources`), **lesson production** (`lessons`) and **assembly** (`assembly`). Topic extraction and curriculum design (phases `topics` to `gate_plan`) come in the next milestone.

The phases, in order: `init → recon → sources → gate_sources → topics → curriculum → gate_plan → scaffold → lessons → assembly → done`. `codelabgen state show` tells you where a course is. Continue from there.

## Before you start

1. Find the course: the directory from the command's arguments, `$CODELABGEN_COURSE`, or the current directory. Every CLI call below takes `--course <dir>`.
2. `codelabgen doctor`: stop and tell the user if a required tool is missing. Docker must show `ok` if any lesson uses services. The `github` line shows how GitHub research will work (`gh`, token or anonymous).
3. `codelabgen state show`.
4. From the `lessons` phase on: `codelabgen curriculum validate` and `codelabgen env check`. If variables are missing, list them and ask the user to fill in `.env`. Don't produce lessons until it passes.

## Research

### Phase `init`: start a course

`/codelabgen:new` gives you the topic, the target directory and optionally the language, the version and the user's own source URLs.

1. The target directory must be given explicitly and must be outside the plugin directory. If it is missing, ask for it.
2. `codelabgen init <dir> --topic "<topic>" --lang <lang> [--version <v>] [--source <url> …]`.
3. `codelabgen state phase recon`.

### Phase `recon`: what is this technology?

1. Run **tech-scout** with the course directory, the topic and the version (if given).
2. Read `.codelabgen/research/overview.md`. If the user gave no version, show the proposed one in a single line and record it: `codelabgen config set version <v>`. If the identity of the technology was ambiguous, confirm it with the user before going on.
3. `codelabgen state phase sources`.

### Phase `sources`: find sources

1. Record the user's own sources first (`user_sources` in `codelabgen config show`): for each, `codelabgen sources add --json '{"url": …, "type": <best guess>, "roles": [<best guess>], "title": <url or page title>, "score": 1.0, "reason": "Provided by the user", "status": "user"}'`.
2. Run one **source-hunter** per source type, **in parallel** (background agents), each with its skill:

   | Type in the prompt | Skill |
   |---|---|
   | official-docs | `source-official-docs` |
   | official-blog and release-notes (also writes deprecations.md) | `source-official-blog` |
   | package-internals | `source-package-internals` |
   | article | `source-articles` |
   | github-repo | `source-github-repos` |
   | qa | `source-qa` |
   | paper-spec | `source-papers-specs` |
   | talk-workshop | `source-talks-workshops` |
   | university | `source-university` |
   | book-course | `source-books-courses` |

3. As hunters finish, give the user one line each (type, how many, any gap). A hunter that fails gets one retry. If it fails again, report the gap and move on.
4. Check that `.codelabgen/research/deprecations.md` exists. If it doesn't, run the official-blog hunter again with only that task.
5. `codelabgen sources render`, then `codelabgen state phase gate_sources`.

### Phase `gate_sources`: the user reviews sources

1. Tell the user the review sheet is ready: `.codelabgen/sources.md` (give the full path). Explain it in two sentences: ticked sources are used, they can untick or tick, and add URLs at the end. Summarize what was found per type, the strongest sources, and the gaps.
2. Wait for the user. They can edit the file, or tell you their changes in the chat. For chat edits, update the ticks in `sources.md` yourself.
3. When the user says it is done: `codelabgen sources apply` and report the result (kept, dropped, added). If the user added sources, run the matching hunter for each new one to check it, fill in a real title, type and roles, and re-add it (re-adding merges).
4. Only when the user explicitly approves: `codelabgen state phase topics --approved`.
5. In this version, stop here. Topic extraction and curriculum design are not built yet. Tell the user the sources are ready and what comes next.

## Lesson production

Ask `codelabgen state next` for work. It returns up to `parallel_modules` lessons, at most one per module, with their current stage. Lessons of one module always run in order, because examples build on each other.

For each lesson, repeat until it is `done`, blocked, or needs the user:

| Current stage | Do this | When it succeeds |
|---|---|---|
| `pending` | Run **example-designer** | `codelabgen state set <id> spec` |
| `spec` | Run `codelabgen scaffold lesson <id>` (copies the earlier lesson's code for an extending example), then **code-author** | `codelabgen state set <id> code` |
| `code` | Run `codelabgen verify <id> --update-state` | Verify itself sets `verified`, or counts a failed attempt: then run **code-fixer** with the JSON it printed and verify again |
| `verified` | Run **readalong-writer** | `codelabgen state set <id> readalong` |
| `readalong` | Run **notes-writer** | `codelabgen state set <id> notes` |
| `notes` | Run **lesson-reviewer** | verdict `pass`: `codelabgen state set <id> reviewed`. Verdict `revise`: see "Rework" |
| `reviewed` | `codelabgen check snippets <id>` must print `ok` | `codelabgen state set <id> done` |

Before recording a stage, check the worker's status JSON and that its artifacts exist. A worker that reports `failed` gets one retry with its notes included in the prompt. After that, block the lesson: `codelabgen state block <id> --reason "<why>"`.

When the verify fix budget runs out, `verify --update-state` blocks the lesson by itself (`"stage": "blocked"` in its output). Stop working on that lesson.

`needs-user` from any worker: block the lesson with the worker's reason and tell the user what is needed.

### Rework after a review

The reviewer returns `rework_from`. Move the lesson back so the right workers run again, with the note pointing at `review.md`:

| `rework_from` | Command | Workers that run again |
|---|---|---|
| `code` | `codelabgen state set <id> spec --note "review round N"` | code-author (fixes `[code]` items), verify, readalong-writer, notes-writer, reviewer |
| `readalong` | `codelabgen state set <id> verified --note "review round N"` | readalong-writer, notes-writer, reviewer |
| `notes` | `codelabgen state set <id> readalong --note "review round N"` | notes-writer, reviewer |

The CLI refuses once the review budget is used up. Then show the user the open items from `review.md` and ask whether to accept the lesson as it is (`codelabgen state set <id> reviewed`) or block it.

After any review, apply the `[spec]` items yourself: edit `.codelabgen/lessons/<id>/spec.yaml` so it matches the verified behaviour (usually an experiment's expected outcome), then `codelabgen state log spec-fixed --lesson <id>`. Later lessons build on these specs.

Every worker in a rework round must read `.codelabgen/lessons/<id>/review.md` and fix its own tagged items. Say so in its prompt.

### Parallel modules

When `state next` returns lessons from different modules, run their pipelines side by side: start each lesson's next worker as a background agent, and when one finishes, record its stage and start that lesson's next step. Never run two lessons of the same module at once. When everything returned by `state next` is done, ask `state next` again.

## Assembly

When `codelabgen state next` reports that all lessons are done, say so and offer to assemble the course (`/codelabgen:build`). When the user agrees, or when you run as part of `/codelabgen:resume`, follow the assembly procedure in the site-assembly skill: glossary, `toc`, `check all`, `site build`, commit, phase `done`.

## Starting a worker

Workers are this plugin's agents (`codelabgen:<name>`). Give each one everything it needs in its prompt. Get the lesson details from `codelabgen curriculum lessons`.

```text
Course directory: <absolute path>
Lesson: <id> "<title>"
Lesson directory: <absolute path>      Module directory: <absolute path>
Python package: <package>              uv project: <project>
Course language: <language>            Technology: <topic> <version>
Example: <new | extends lesson X>
<For rework: Review round N; fix the items tagged [<part>] in .codelabgen/lessons/<id>/review.md>
<For code-fixer: the full JSON printed by codelabgen verify>
Task: <one line, e.g. "Write the lesson spec">
```

Wait for the status JSON at the end of the worker's reply. If it is missing or malformed, treat the run as `failed`.

## Keeping the user informed

After each stage, send one short line: lesson, stage reached, anything notable. When the work stops (all done, blocked or waiting for the user), summarize with `codelabgen state show`.
