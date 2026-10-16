---
name: source-evaluation
description: The common procedure for every codelabgen source hunter — how to fetch and inspect candidate sources, score them, assign roles, and record them with `codelabgen sources add`. Load together with the skill for the source type being searched.
user-invocable: false
---

# Finding and recording sources

A course is only as good as its sources. Your job is to find the best few sources of one type, check each one, and record it so the user can review the list. Quality beats quantity: 5 excellent sources are worth more than 20 mediocre ones.

## Inputs

Before searching, read:
- `.codelabgen/config.yaml`: topic, pinned `version`, course `language`, `budgets.sources_per_type`
- `.codelabgen/research/overview.md`: what the technology is, its packages, docs and repo URLs
- `codelabgen sources list --brief`: what is already recorded, so you don't propose duplicates

## Tools

| Need | Use |
|---|---|
| Web search | WebSearch. Run several focused queries rather than one broad one |
| Read a page | `codelabgen fetch <url>`, then Read the cached file it prints. The cache is shared, so other agents reuse your fetches |
| Large documents (`llms-full.txt`, PDFs) | Grep the cached file for headings and keywords; don't Read it whole |
| GitHub | `codelabgen github repos/code/meta/issues …` (JSON output) |
| The library's own code | `codelabgen repo clone <repo>` at the pinned version |
| Package versions | `codelabgen pkg-info <pypi\|npm\|crates\|go> <name>` |

Fall back to WebFetch only for a page `codelabgen fetch` can't read.

## Check every source before recording it

Open it (fetch and read at least the beginning and the structure). Record a source only if you have seen that:
- it is reachable and really is what the title says
- it is about this technology, and you know which version it targets (from the date, the version mentioned, or the API it uses)
- it adds something: an explanation, examples, a structure or pitfalls that other recorded sources don't already cover

## Score (0–1)

Start from these criteria, then use judgment:

| Criterion | Strong | Weak |
|---|---|---|
| Authority | Official docs or maintainers, recognized experts, universities | Anonymous, content farms, AI-generated filler |
| Version fit | Targets the pinned version or one compatible with it | Older major version, removed APIs |
| Depth | Explains why, covers edge cases | Restates the quickstart |
| Runnable examples | Complete code that runs | Fragments, pseudocode |
| Freshness | Updated within the life of the pinned major version | Predates it |

As a guide: official docs for the pinned version score 0.9–1.0, a strong independent tutorial 0.6–0.8, a useful but dated piece 0.4–0.6. Below 0.4, don't record it. Sources at 0.6 or above start ticked on the review sheet.

## Roles

Give each source every role it serves well:
- `structure`: shows how the topic is usually taught (tables of contents, course outlines, tutorial sequences)
- `code-truth`: shows how the API really behaves in the pinned version (official examples, tests, reference docs)
- `concepts`: explains ideas and the reasoning behind them
- `pitfalls`: common mistakes, confusing behaviour, known problems

## Recording

Add each source as one JSON object:

```bash
codelabgen sources add --course <dir> --json '{"url": "https://docs.langchain.com/oss/python/langgraph/graph-api", "type": "official-docs", "roles": ["code-truth", "concepts"], "title": "Graph API overview", "language": "en", "version": "1.x", "date": "2026-09", "score": 0.95, "reason": "Official reference for StateGraph, nodes, edges and reducers, with runnable snippets."}'
```

- `type` is the type you were asked to search. `codelabgen schema show source` lists all fields.
- `title`: the real title of the page, repo, book or talk.
- `reason`: one sentence in English saying what the source gives the course. The user reads it when deciding.
- `language` of the source itself (ISO code). `date` is YYYY-MM or YYYY-MM-DD, when you know it.
- Adding the same URL again merges the entries, so re-adding is safe.

Stay within `budgets.sources_per_type` for your type, unless the user's own sources push past it.

## Finish

End with the status JSON (see the state-protocol skill), for example:

```json
{"lesson": null, "status": "ok", "stage": "sources", "artifacts": [".codelabgen/sources.jsonl"], "notes": "official-docs: 6 sources added, best: Graph API overview (0.95)"}
```

Mention gaps in `notes`, such as "no university material found", so the orchestrator can tell the user.
