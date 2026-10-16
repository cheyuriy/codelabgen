---
name: source-books-courses
description: How to find books, open online courses, vendor courses and "by example" sites about a technology for a codelabgen course, and extract their structure (tables of contents, lesson sequences, example style). Source type `book-course`.
user-invocable: false
---

# Books and courses (`book-course`)

Other teachers have already solved the problem we're solving: in what order to teach this, and with what examples. You don't need their full text. Their **tables of contents and lesson lists** are what the curriculum architect will compare.

## Where to look

| Kind | Where |
|---|---|
| Books | Publisher pages (O'Reilly, Manning with MEAP, Packt, Apress, No Starch, Pragmatic, and for Russian Питер, ДМК Пресс, БХВ), Amazon or Goodreads listings, Leanpub. The TOC is usually public. |
| Open courses | Coursera, edX, Udemy (the curriculum is public), Stepik, Open Education, YouTube playlists |
| Vendor courses | The maintainers' academy or learning paths, for example LangChain Academy, DeepLearning.AI short courses |
| "By example" sites and exercise tracks | Go by Example, Rust by Example, Exercism tracks, Learn X in Y minutes: models of small, focused examples |

Search in English and in the course language: `<topic> book`, `<topic> course`, `<topic> книга`, `<topic> курс`.

## What to extract

Fetch the page with the table of contents or curriculum. In `reason`, write the structure compactly, because that is the useful part:

```
"reason": "Manning MEAP 2026 for LangGraph 1.x: 1 graphs & state, 2 routing, 3 tools, 4 memory/persistence, 5 human-in-the-loop, 6 multi-agent, 7 deployment. Starts with a chat agent, adds tools in ch3."
```

- Note what the example storyline is, if there is one, and how small the examples are.
- Record the version and date: a TOC for an older major version still shows a teaching order, but say it is dated.
- Roles: `structure` always. Add `concepts` only if the full text is openly available and good.

Prefer recent material for the pinned major version, and the vendor's own course when one exists.
