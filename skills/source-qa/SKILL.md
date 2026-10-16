---
name: source-qa
description: How to find the questions, errors and confusing behaviour learners hit with a technology — GitHub issues and discussions of the official repo, Stack Overflow, forums — as pitfalls material for a codelabgen course. Source type `qa`.
user-invocable: false
---

# Questions and problems (`qa`)

This hunter finds what goes wrong in practice. Its sources feed the "common mistakes" callouts in the notes and the experiments in the read-along. The role is almost always `pitfalls`.

## GitHub issues and discussions

1. The official repo is in `research/overview.md`.
2. `codelabgen github issues <repo>` saves the most-reacted issues as Markdown in the cache and prints the path. Read it. Narrow it down with `--query`, for example `--query "label:question"`, `--query "checkpointer"`, or the names of core concepts.
3. `codelabgen github issues <repo> --discussions` does the same for discussions (Q&A and ideas), if the repo uses them. Many projects keep their help forum elsewhere (a Discourse forum, Discord); search for it, and if it is public and indexable, treat it like Stack Overflow.
4. Look for patterns: the same misunderstanding asked many times, errors with confusing messages, behaviour that surprised people, breaking changes that hit many users.

## Stack Overflow

- WebSearch `site:stackoverflow.com <topic> <concept>` for the core concepts, or browse the tag (`https://stackoverflow.com/questions/tagged/<tag>?tab=Votes`).
- Prefer high-voted questions with an accepted answer that still holds for the pinned version. Answers for older versions are still pitfalls ("this used to work"), but say so.

## What to record

Don't record single issues. Record **collections** that are useful as a whole:
- the cached top-issues file as one source: url `https://github.com/<repo>/issues?q=sort%3Areactions-%2B1-desc`, with a `reason` summarizing the main recurring problems
- a topic-specific issue search, when one concept clearly causes many problems
- the Stack Overflow tag, sorted by votes, and individual Q&As only when they are excellent explanations
- the official forum's FAQ or most-viewed threads

In `reason`, name the concrete pitfalls found, for example: "Recurring: msgpack serialization errors for custom state types; confusion between updates and values stream modes; thread_id missing from config."
