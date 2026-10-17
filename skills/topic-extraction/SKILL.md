---
name: topic-extraction
description: How to read a source for a codelabgen course and turn it into topic records (codelabgen topics add) — names, summaries, difficulty, prerequisites, APIs and evidence links — that the curriculum architect merges into a course plan.
user-invocable: false
---

# Extracting topics from a source

Topics are the raw material of the curriculum. Each record says: this source teaches this concept, at this difficulty, using these APIs, and here is where. The architect merges topics from all sources and sees which concepts matter (many sources cover them), in what order they are taught, and what depends on what.

## Reading the source

- Find the cached copy first: `codelabgen fetch <url>` returns the cache path immediately if another agent already fetched it.
- **Docs sections:** read the section page and the subpages it lists (fetch them).
- **Repos** (`github-repo`, `package-internals`): `codelabgen repo clone <url>`, then look at the README, the folder structure and a few representative files. Don't read everything.
- **Large files** (`llms-full.txt`, PDFs, transcripts): grep for headings and read the relevant parts.
- **Book and course pages:** the table of contents is the content.
- **Q&A collections:** the cached issues file. Topics here are problems, for example "serialization errors for custom state types".

## Topic records

Add the topics of one source with one call. It replaces earlier topics for that source:

```bash
codelabgen topics add --course <dir> --source <source-id> --json '[
  {"name": "Conditional edges", "summary": "Route to different nodes based on state with add_conditional_edges and a routing function.", "difficulty": 2, "prerequisites": ["StateGraph", "Nodes and edges"], "apis": ["add_conditional_edges"], "evidence_url": "https://docs.langchain.com/oss/python/langgraph/graph-api#conditional-edges"}
]'
```

- **name:** the canonical concept name, in English and preferably in the technology's own terms: "Checkpointer", "Conditional edges", "Human-in-the-loop interrupts". Reuse the same names other sources use (check `.codelabgen/topics/summary.md` if it exists), so topics merge.
- **summary:** one sentence: what the learner can do with it.
- **difficulty** (1–5):
  1. first contact, needed by everything
  2. core feature used in most real projects
  3. intermediate: combining features, configuration choices
  4. advanced: internals, performance, unusual patterns
  5. expert: edge cases, extending the framework
- **prerequisites:** other topic names this one builds on.
- **apis:** the main classes, functions or parameters involved, exactly as spelled in code.
- **evidence_url:** where in the source the topic is taught (an anchor or file path).

Usually 5–25 topics per source. A focused article may give 3, a docs section or a book TOC 20 or more. Don't split hairs ("add_node with a name" and "add_node without a name" are one topic), and don't lump unrelated things together.

## Then the digest

Write the digest following the source-digest skill. Do the topics and the digest in the same pass, while the source is fresh.

## If the registry entry is wrong

A user-added source may have a placeholder title or a guessed type. Re-add it with `codelabgen sources add` using the same URL and the real title: the entries merge and the title is updated. If the source is useless (dead link, off topic), say so in your status notes and skip it. The orchestrator decides what to do.
