---
name: codelabgen-orchestrator
description: Runs and resumes the codelabgen pipeline from the main session — follows `codelabgen state next`, dispatches the worker agents with task tracking, records state through the `codelabgen` CLI, handles verify failures, reviews and rework, and stops for the user at gates. Load when a /codelabgen command asks for it.
user-invocable: false
---

# codelabgen orchestrator

You drive course generation from the main session. Only you start subagents, and only you change course state (see the state-protocol skill). Workers do one job each and end with a status JSON.

The phases, in order: `init → recon → sources → gate_sources → topics → curriculum → gate_plan → scaffold → lessons → assembly → done`. Every command (new, sources, plan, lesson, build, resume) runs the same loop from wherever the course is.

## Before you start

1. Find the course: the directory from the command's arguments, `$CODELABGEN_COURSE`, or the current directory. Every CLI call below takes `--course <dir>`.
2. `codelabgen doctor`: stop and tell the user if a required tool is missing. Docker must show `ok` if any lesson uses services. The `github` line shows how GitHub research will work (`gh`, token or anonymous).
3. `codelabgen state show`, then `codelabgen state next`.

## The main loop

`codelabgen state next` is the source of truth for what remains. It reads the state **and** the files on disk, so it never repeats finished work. Its JSON has:
- `phase`: where the course is
- `actions`: what to do now, in order. Each has a `do`:
  - `run-agent`: start the named worker, with the `task` key and `args` (see "Starting a worker")
  - `command`: a codelabgen command you run yourself
  - `ask-user`: stop and talk to the user (review gates, missing secrets, a version to confirm)
  - `advance`: move to the next phase (`run` holds the exact command; `--approved` only after the user approved)
- `lessons` / `blocked` in the `lessons` phase: the work items (see "Lesson production")
- `interrupted`: tasks whose worker stopped midway in an earlier session

Repeat: run `state next`, do its actions (independent `run-agent` actions in parallel, up to `budgets.parallel_agents` at once, default 4), then run `state next` again. Stop when it asks for the user, or when the phase is `done`. The phase sections below say how to do each step well; `state next` says which steps are left.

## Tasks and resuming

Every worker run is a **task**:
1. Before starting the worker: `codelabgen state task start <task> [--lesson <id>]`. It prints the attempt number.
2. After it succeeds and you have recorded its result: `codelabgen state task done <task>`.
3. If it fails: `codelabgen state task fail <task> --note "<why>"`. One retry is allowed; the next `task start` counts it.

A task that is still `running` when a session starts was **interrupted**: the session ended while its worker was busy. `state next` marks it (`"interrupted": true`). Its worker may have left partial work: a half-written spec, some of the code, a digest without all its sections, a few sources already added. When you restart such a task, say so in the worker's prompt: "A previous attempt was interrupted. Check what it left in <paths>, keep what is correct, and complete the rest." Never just delete partial work.

Lesson tasks are named `lesson:<id>:<stage being produced>`, for example `lesson:1.2:code` for the code-author run. `state next` gives the key with each lesson.

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
2. Run one **source-hunter** per source type (task `sources:<type>`), **in parallel** (background agents), each with its skill. `state next` lists only the types not done yet:

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
2. Run one **topic-extractor** per batch (the `task` key comes from `state next`), up to `parallel_agents` at a time in the background. When one finishes, start the next batch.
3. `codelabgen sources digests` must print `all digests present`. Give a missing digest one retry. If it fails again, mark the source as dropped in `sources.md`, run `codelabgen sources apply`, and tell the user.
4. `codelabgen topics merge` and `codelabgen sources index`. Tell the user in one line how many topics were found.
5. `codelabgen state phase curriculum`.

### Phase `curriculum`: plan the course

1. Run **curriculum-architect** (task `curriculum:architect`). Pass on any wishes the user stated earlier (scope, depth, things to include or skip), and the `problems` from `state next` if an earlier draft is invalid.
2. Run **runtime-planner** (task `curriculum:runtime`).
3. `codelabgen curriculum validate`, `codelabgen sources index` (it now shows which lessons use which source), `codelabgen curriculum render`.
4. `codelabgen state phase gate_plan`.

### Phase `gate_plan`: the user reviews the plan

1. Show the user the plan: the path of `.codelabgen/plan.md`, plus a compact summary in the chat (modules with their lessons, one line each; the example storyline; the services). Ask the runtime planner's **questions** from `.codelabgen/research/runtime.md`, numbered, with the suggested defaults. These are usually which LLM provider and model to use. Tell the user which keys they will need.
2. Handle feedback in rounds:
   - Structure changes ("merge 2.3 and 2.4", "add a lesson on streaming", "skip deployment"): `codelabgen state task reset curriculum:architect` and `… curriculum:runtime`, run **curriculum-architect** with the feedback, then **runtime-planner**, then validate and render again.
   - Small wording changes: edit `curriculum.yaml` yourself, then validate and render.
   - Answers to the questions: run **runtime-planner** with the answers. It records them (`codelabgen config external add …`) and adds the variables to `env`. Then validate and render.
3. Only when the user explicitly approves the plan and every question is answered: `codelabgen state phase scaffold --approved`.

### Phase `scaffold`: prepare the course directory

1. `codelabgen scaffold course`. It writes the module workspaces and lesson directories, `docker-compose.yml`, `.env.example` and `.env`, initializes git, and registers the lessons.
2. `codelabgen toc`, which writes `run.sh` and the READMEs.
3. If the course needs secrets: tell the user to fill them in the course `.env` (full path), listing each variable and where to get it (`codelabgen env list`). Wait until `codelabgen env check` prints `ok`.
4. `codelabgen state phase lessons`, then continue with lesson production.

## Lesson production

`codelabgen state next` returns up to `parallel_modules` lessons, at most one per module, each with its current stage, the `task` key of the next step, and whether that step was `interrupted`. Lessons of one module always run in order, because examples build on each other.

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

Wrap each worker run in its task (`state task start` before, `state task done` after recording the stage). `verify` is not a worker: run it directly. Before recording a stage, check the worker's status JSON and that its artifacts exist. A worker that reports `failed` gets one retry with its notes included in the prompt. After that, block the lesson: `codelabgen state block <id> --reason "<why>"`.

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

## Extensions

`/codelabgen:extend <dir> "<request>"` extends a finished course. `state next` drives it like everything else: while an extension is before lesson production, it returns `extension` and that extension's actions.

1. **Start:** `codelabgen extend start "<request>"`. It refuses if lessons are unfinished or the course repo has uncommitted changes. Tell the user why and stop.
2. **`gaps`:** run **gap-analyst** (task `ext<n>:gaps`), then `codelabgen extend stage research`.
3. **`research`:** one **source-hunter** per entry of `hunt.yaml` (tasks `ext<n>:hunt:<type>`), passing its `focus`. Then `codelabgen sources keep-proposed --min-score 0.6` and `codelabgen extend stage digests`.
4. **`digests`:** **topic-extractor** batches as in phase `topics`, then `topics merge`, `sources index`, and `extend stage delta`.
5. **`delta`:** **curriculum-architect** in extend mode (task `ext<n>:architect`, with the proposal path), then **runtime-planner** in extend mode (task `ext<n>:runtime`), then `codelabgen extend diff` and `extend stage gate`.
6. **`gate`:** show the user `.codelabgen/extensions/<n>/delta.md`: the new lessons, rewritten lessons, renamed ones, renumbering, and lessons to re-check. Also list the sources kept during this extension and ask about any new runtime questions. Feedback goes back to the architect (`codelabgen state task reset ext<n>:architect`). When the user approves: `codelabgen extend apply`. Add `--allow-renumber` only if the delta renumbers lessons and the user explicitly agreed to it. For new secrets, wait for `codelabgen env check`.
7. **Lessons:** the course is back in phase `lessons`. Produce the new and rewritten lessons as usual.
   - **Stale lessons** (`"stage": "stale"` in `state next`): run `codelabgen verify <id>`. If it fails, `codelabgen state set <id> spec --note "stale: <cause>"` and redo from the code. If it passes, run **lesson-reviewer** with the note "This lesson builds on lesson X, which was rewritten; check that it still agrees". On pass: `state set <id> reviewed`, then `done`. On revise: rework as for any review.
8. **Assembly** as usual. Commit with a message naming the extension: `codelabgen commit -m "Extension <n>: <request>"`. Then `codelabgen extend finish`.

## Starting a worker

Workers are this plugin's agents (`codelabgen:<name>`). Give each one everything it needs in its prompt. Get the lesson details from `codelabgen curriculum lessons`. For research and curriculum workers, pass the course directory, the course language, the technology and version, and the `args` from `state next`.

```text
Course directory: <absolute path>
Lesson: <id> "<title>"
Lesson directory: <absolute path>      Module directory: <absolute path>
Runtime: <python-uv | node | go>       Package / project: <package> / <project>
Course language: <language>            Technology: <topic> <version>
Example: <new | extends lesson X>
Lesson sources (digests in .codelabgen/sources/): <the node's sources>
<For rework: Review round N; fix the items tagged [<part>] in .codelabgen/lessons/<id>/review.md>
<For code-fixer: the full JSON printed by codelabgen verify>
<For an interrupted task: A previous attempt was interrupted; check and complete its partial work in …>
Task: <one line, e.g. "Write the lesson spec">
```

Wait for the status JSON at the end of the worker's reply. If it is missing or malformed, treat the run as `failed`.

## Keeping the user informed

After each step, send one short line: what finished, anything notable. When the work stops (all done, blocked or waiting for the user), summarize with `codelabgen state show`. At the end of a course, `codelabgen report` gives the generation summary (timings, verify runs, review rounds, unfinished tasks), and `codelabgen eval` scores the course against the rubric. Show the user the overall score, the dimensions and anything missing, and point them to `.codelabgen/eval-human.md` for their own review of two sampled lessons.

## Budgets

`budgets` in `.codelabgen/config.yaml`: `fix_attempts` (verify failures before a lesson blocks), `review_rounds`, `parallel_modules` (lessons in flight), `parallel_agents` (agents at once in research and topics), `sources_per_type`. The CLI enforces the first two. Respect the last three yourself.
