---
name: site-assembly
description: How a codelabgen course is assembled into its readable form — generated READMEs and table of contents, run.sh, the glossary, the MkDocs site and its GitHub-compatible rendering rules, the final checks and the commit. Load for the assembly phase and /codelabgen:build.
user-invocable: false
---

# Assembling the course

A course is read in two places: on GitHub (or in an IDE) as plain Markdown, and as an MkDocs Material website. Both must look good. Assembly generates the pages that tie the lessons together, checks everything, builds the site and commits.

## What is generated (never edit by hand)

`codelabgen toc` writes, from the curriculum and lesson specs:

| File | Content |
|---|---|
| `README.md` | Course title, description, getting started (`.env`, `./run.sh`, the site), contents with summaries |
| `<module>/README.md`, section READMEs | Title, summary, objectives, lesson list |
| `<lesson>/README.md` | Summary, "continues lesson X" note, objectives, links to notes / read-along / code, how to run and test, previous/next |
| `mkdocs.yml` | Site config and nav (only pages that exist) |
| `run.sh` | `./run.sh <id>`, `./run.sh test <id>`, `./run.sh list`, `./run.sh site serve` |
| `assets/` | MathJax setup, asciinema player hook and script |
| `GLOSSARY.md`, `assets/glossary-abbr.md` | From `.codelabgen/glossary.yaml` (`codelabgen glossary build`) |

Labels in these files follow the course language. To change their wording, change the generator, not the files.

## How Markdown features render

| Feature | Written as | GitHub | Site |
|---|---|---|---|
| Code from the lesson | `<!-- snippet: path#region -->` markers, filled by `codelabgen snippets sync` | Code block | Code block with highlighting and a copy button |
| Callouts | `> [!NOTE]`, `> [!TIP]`, `> [!WARNING]`, `> [!IMPORTANT]` | Native alerts | Admonitions (mkdocs-callouts) |
| Mermaid | ` ```mermaid ` | Native | Native (Material) |
| Math | `$…$`, `$$…$$` | Native | MathJax (arithmatex) |
| Glossary terms | A link on first use; definition in `GLOSSARY.md` | Link | Link, plus a tooltip on every use of the term or an alias |
| D2 / Graphviz | `![…](diagrams/x.svg)` | Image | Image |
| Recordings | `![…](generated/x.gif)` | Animated GIF | Interactive asciinema player |
| Hidden answers | `<details><summary>…</summary>…</details>` | Native | Native |

Not allowed, because GitHub shows them as broken text: `!!!` / `???` admonitions, `===` content tabs, `(1)!` code annotations, `--8<--` includes. `codelabgen check render` finds them.

Site details:
- `use_directory_urls: false`, so relative links and paths work the same as on GitHub.
- Heading anchors use GitHub's rules, including Cyrillic text (`#граф-состояний`).
- Code files are part of the site, so links to `../src/<package>/graph.py` work there too.
- `strict: true`: any broken link or missing page fails the build.

## The assembly procedure

Run from the main session, with `--course <dir>` on every command:

1. **All lessons done:** `codelabgen state show` shows every lesson `done`, then `codelabgen state phase assembly`.
2. **Generate:** `codelabgen glossary build`, then `codelabgen toc`.
3. **Check:** `codelabgen check all`. Fix every problem in the page that has it. For problems in a lesson's docs, send that lesson back (`codelabgen state set <id> verified` or `readalong` with a note) and let its writer fix it, then return here. Problems in generated files mean a generator bug: report it to the user.
4. **Build the site:** `codelabgen site build` must succeed (strict mode).
5. **Commit:** `codelabgen commit -m "<message>"`, for example "Course: LangGraph на практике, lessons 1.1–1.3".
6. **Done:** `codelabgen state phase done`. Tell the user how to read the course: the course `README.md`, `./run.sh site serve`, and `./run.sh <id>` to run a lesson.

`codelabgen site serve` starts a local preview at http://127.0.0.1:8000 with live reload. It runs until stopped, so start it in the background only when the user asks for a preview.

## Optional tools

`codelabgen doctor` lists them. Without `d2` or `dot`, diagrams in those formats can't be rendered, so lessons should use Mermaid. Without `asciinema` and `agg`, recordings are skipped (verify logs "skipped"), and lessons must not link to recordings that don't exist.
