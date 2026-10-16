---
name: source-official-blog
description: How to find a technology's official blog posts with examples, and — mandatory — its changelogs, release notes and migration guides, producing `.codelabgen/research/deprecations.md`, the list of deprecated and renamed APIs. Source types `official-blog` and `release-notes`.
user-invocable: false
---

# Official blog and release notes (`official-blog`, `release-notes`)

This hunter has two jobs. The second one is mandatory.

## 1. Blog posts with examples (`official-blog`)

- Find the vendor's or maintainers' blog: links from the docs site, the homepage, the GitHub org's README.
- Search it for posts that **teach**: feature introductions with code, design rationale ("why we built X"), case studies with runnable examples. Skip announcements, funding news and marketing.
- Prefer posts about the pinned major version. An older post can still be worth recording for its reasoning (`concepts`), but not for its code.
- Roles: usually `concepts`, plus `code-truth` when the code matches the pinned version and `pitfalls` for "lessons learned" posts.

## 2. Changes between versions (`release-notes`, mandatory)

Find what changed in the technology up to the pinned version:
- the changelog or GitHub releases (`codelabgen github meta` gives the repo; releases live at `https://github.com/<repo>/releases`), the "What's new" and migration guide pages in the docs, deprecation policy pages
- focus on the current major version and the one before it: that is what outdated tutorials, LLM training data and Stack Overflow answers still use

Record the migration guides and the most informative release notes as `release-notes` sources (roles `code-truth`, `pitfalls`).

Then **write `.codelabgen/research/deprecations.md`**: the APIs a course author must not use, and what replaced them.

```markdown
# Deprecated and changed APIs — LangGraph up to 1.2.15

| Old API | Replacement | Since | Source |
|---|---|---|---|
| `from langgraph.checkpoint.memory import MemorySaver` | `InMemorySaver` (same module) | 1.0 | [Migration guide](https://…) |
| `graph.compile(checkpoint_during=…)` | `durability="sync" \| "async" \| "exit"` at invoke time | 1.0 | [Release notes 1.0](https://…) |

## Behaviour changes worth knowing
- …
```

- Only entries you have seen in a release note, migration guide or the changelog. Link each one.
- Confirm in the pinned version's code when in doubt: `codelabgen repo clone <repo>`, then grep for the old name and look for a deprecation warning.
- Include renamed parameters and changed defaults, not only removed functions.
- If you find nothing, write the file anyway, saying what you checked.
