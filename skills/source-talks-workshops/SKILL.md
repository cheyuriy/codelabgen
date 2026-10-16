---
name: source-talks-workshops
description: How to find conference talks, meetup recordings and hands-on workshops about a technology for a codelabgen course — especially workshops with a step-by-step repository — and read them through transcripts. Source type `talk-workshop`.
user-invocable: false
---

# Talks and workshops (`talk-workshop`)

Talks by maintainers explain design decisions you won't find in the docs. Workshops are often small courses in themselves: a repo with numbered steps is a ready-made view of how to teach the topic.

## Search

- WebSearch and YouTube: `<topic> talk`, `<topic> conference`, `<topic> workshop`, `<topic> tutorial PyCon` (or JSConf, GopherCon, KubeCon, depending on the ecosystem), and the vendor's own events and channels.
- GitHub: `codelabgen github repos "<topic> workshop"`. Look for repos with `step-01`, `exercises/`, `solutions/` folders.
- In the course language too, for example Russian conferences and meetups (`<topic> доклад`, `<topic> воркшоп`).

## Reading a talk

`codelabgen transcript <video url>` saves the subtitles as text in the cache (it uses `yt-dlp`, through `uvx` when not installed). Skim the transcript for the talk's structure and its key claims, and check that the speaker is a maintainer or an experienced user. Talks older than the pinned major version are only worth recording for their reasoning.

## What to record

- **Workshops with a step-by-step repo:** the repo URL (`structure`, `code-truth` when on the pinned version). In `reason`, describe the steps briefly.
- **Talks by maintainers on design and internals** (`concepts`).
- **Talks on production experience** (`pitfalls`).

Prefer recordings with good subtitles, since agents can't watch video. Record the talk's page (the YouTube or conference URL) with the speaker and event in `title`.
