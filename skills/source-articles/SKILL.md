---
name: source-articles
description: How to find good third-party articles about a technology for a codelabgen course — Medium, Habr, dev.to, personal and company engineering blogs, and comparison articles — in the course language and in English, while filtering out low-quality posts. Source type `article`.
user-invocable: false
---

# Articles (`article`)

Independent articles bring what official docs often lack: an outside view, real projects, war stories and comparisons. They also contain the worst content on the web, so filter hard.

## Where and how to search

Run WebSearch with several queries, in **English and in the course language**:
- tutorials with code: `"<topic>" tutorial example`, `<topic> step by step`, Russian: `<topic> пример`, `<topic> разбор`, `site:habr.com <topic>`
- deep dives: `<topic> internals`, `how <topic> works under the hood`, `<topic> architecture`
- experience reports: `<topic> in production`, `lessons learned <topic>`, `<topic> pitfalls`, `<topic> подводные камни`
- **comparisons:** `<topic> vs <alternative>`, `when not to use <topic>`, `<topic> alternatives`. Take the alternatives from `research/overview.md`.
- platforms: Medium, dev.to, Habr, Hashnode, Substack, company engineering blogs. Personal blogs of the maintainers are often the best of all.

## Filter

Read each candidate before recording it. Reject:
- AI-generated filler: generic intros, no specifics, code that wouldn't run
- copies of the official quickstart with nothing added
- posts for an old major version with APIs that have since changed, unless the reasoning itself is valuable (then `concepts` only, and say so)
- paywalled content you couldn't read

Signals of quality: a real project, complete code or a linked repo, a named author with other work on the topic, discussion of trade-offs, a recent date.

## Roles

- deep dives and explanations: `concepts`
- comparison articles: `concepts`. In `reason`, say what it is compared with and what that teaches.
- production stories and pitfalls posts: `pitfalls`
- tutorials with current, working code: `code-truth`, `structure` (when they show a learning sequence)

Expect most articles to score 0.5–0.8. Record the language of each article.
