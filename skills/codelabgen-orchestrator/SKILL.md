---
name: codelabgen-orchestrator
description: Runs the codelabgen pipeline from the main session — dispatches the worker agents, records state through the `codelabgen` CLI, handles verify failures, reviews and rework, and stops for the user at gates. Load when a /codelabgen command asks for it.
user-invocable: false
---

# codelabgen orchestrator

You drive course generation from the main session. Only you start subagents, and only you change course state (see the state-protocol skill). Workers do one job each and end with a status JSON.

> This version covers every phase. `/codelabgen:resume` (continue any course from its state) comes in the next milestone; until then each command below continues from where the course is.

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
4. Only when the user explicitly approves: `codelabgen state phase topics --approved`, then continue with phase `topics`.

## Curriculum

### Phase `topics`: digests and topics

1. `codelabgen sources batches --size 5`: groups of source ids that still need a digest (on a resumed run, only the missing ones).
2. Run one **topic-extractor** per batch, up to 4 at a time in the background. When one finishes, start the next batch.
3. `codelabgen sources digests` must print `all digests present`. Give a missing digest one retry. If it fails again, mark the source as dropped in `sources.md`, run `codelabgen sources apply`, and tell the user.
4. `codelabgen topics merge` and `codelabgen sources index`. Tell the user in one line how many topics were found.
5. `codelabgen state phase curriculum`.

### Phase `curriculum`: plan the course

1. Run **curriculum-architect**. Pass on any wishes the user stated earlier (scope, depth, things to include or skip).
2. Run **runtime-planner**.
3. `codelabgen curriculum validate`, `codelabgen sources index` (it now shows which lessons use which source), `codelabgen curriculum render`.
4. `codelabgen state phase gate_plan`.

### Phase `gate_plan`: the user reviews the plan

1. Show the user the plan: the path of `.codelabgen/plan.md`, plus a compact summary in the chat (modules with their lessons, one line each; the example storyline; the services). Ask the runtime planner's **questions** from `.codelabgen/research/runtime.md`, numbered, with the suggested defaults. These are usually which LLM provider and model to use. Tell the user which keys they will need.
2. Handle feedback in rounds:
   - Structure changes ("merge 2.3 and 2.4", "add a lesson on streaming", "skip deployment"): run **curriculum-architect** with the feedback, then **runtime-planner**, then validate and render again.
   - Small wording changes: edit `curriculum.yaml` yourself, then validate and render.
   - Answers to the questions: run **runtime-planner** with the answers. It records them (`codelabgen config external add …`) and adds the variables to `env`. Then validate and render.
3. Only when the user explicitly approves the plan and every question is answered: `codelabgen state phase scaffold --approved`.

### Phase `scaffold`: prepare the course directory

1. `codelabgen scaffold course`. It writes the module workspaces and lesson directories, `docker-compose.yml`, `.env.example` and `.env`, initializes git, and registers the lessons.
2. `codelabgen toc`, which writes `run.sh` and the READMEs.
3. If the course needs secrets: tell the user to fill them in the course `.env` (full path), listing each variable and where to get it (`codelabgen env list`). Wait until `codelabgen env check` prints `ok`.
4. `codelabgen state phase lessons`, then continue with lesson production.

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
Lesson sources (digests in .codelabgen/sources/): <the node's sources>
<For rework: Review round N; fix the items tagged [<part>] in .codelabgen/lessons/<id>/review.md>
<For code-fixer: the full JSON printed by codelabgen verify>
Task: <one line, e.g. "Write the lesson spec">
```

Wait for the status JSON at the end of the worker's reply. If it is missing or malformed, treat the run as `failed`.

## Keeping the user informed

After each stage, send one short line: lesson, stage reached, anything notable. When the work stops (all done, blocked or waiting for the user), summarize with `codelabgen state show`.
