---
name: source-digest
description: How to write the digest of one source for a codelabgen course (.codelabgen/sources/<id>.md) — a short, structured summary that later agents use to know what the source covers, where its examples are, and where to dig deeper when the course is extended.
user-invocable: false
---

# Writing a source digest

A digest is a source's index card. Every later agent reads digests instead of the source itself: the curriculum architect to plan, the lesson writers to find material, and the gap analyst to extend the course months later. Make it accurate, specific and short: 30–80 lines.

Write it in **English**, whatever the course language is.

## Format

`.codelabgen/sources/<id>.md`, with the id exactly as in `codelabgen sources list`:

```markdown
---
id: official-docs--docs-langchain-com--3cfc8e
url: https://docs.langchain.com/oss/python/langgraph/graph-api
type: official-docs
roles: [code-truth, concepts]
title: Graph API overview
version: "1.x"
fetched: 2026-10-16
score: 0.95
---

## Summary
What the source is, its angle and its depth, in 2–4 sentences. Whom it is for, and how
current it is relative to the pinned version.

## Topics covered
- **StateGraph and state schemas**: TypedDict, Pydantic and dataclass schemas, input/output schemas ([#state](https://…#state))
- **Reducers**: `Annotated` with `operator.add`, `add_messages`, custom reducers (#reducers)
- …

## Code examples
- Minimal graph with two nodes and a conditional edge (#conditional-edges): complete, runnable
- `examples/persistence/postgres.py` in the repo: PostgresSaver setup with a connection pool
- …

## Gaps / dig deeper
- Skims the `Send` API; the full treatment is on the "Map-reduce" page (not fetched): https://…
- No coverage of async execution
- Follow-up queries: "langgraph durability modes", "langgraph subgraph state mapping"
```

## Rules

- **Topics covered** keeps the source's own order. For a book TOC or a course outline, that order is the point. Link sections with anchors or paths whenever you can, so a writer can jump straight there.
- **Code examples** lists only examples that exist, with where to find them, and says whether they are complete and runnable.
- **Gaps / dig deeper** is for the future: what the source skips or only mentions, linked pages you didn't read, versions it doesn't cover, and search queries that would continue the research.
- Never pad. If a source turns out to be thin, say so in the summary. The orchestrator may drop it.
- Copy the front matter fields from the registry entry. Set `fetched` to today.
