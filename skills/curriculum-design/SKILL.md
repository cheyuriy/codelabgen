---
name: curriculum-design
description: How to design a codelabgen course curriculum (.codelabgen/curriculum.yaml) from the extracted topics and source digests — modules and lessons from simple to complex, one idea per lesson, objectives, prerequisites, the example storyline, and the sources each lesson builds on.
user-invocable: false
---

# Designing the curriculum

The curriculum decides what the course teaches and in what order. Every lesson will become a runnable example, a code walkthrough and a book-style chapter. So each lesson must be one teachable idea that a single, focused example can show.

## Inputs

- `.codelabgen/research/overview.md`: the technology, its core concepts, prerequisites, recent changes
- `.codelabgen/topics/summary.md`: every topic found, how many sources cover it, difficulty, prerequisites
- `.codelabgen/sources/index.md`, then the digests with role `structure`: how the official tutorials, books and courses order the material. The official docs' tutorial sequence carries the most weight.
- `.codelabgen/research/deprecations.md`: never plan a lesson around a deprecated API
- the user's wishes, if the orchestrator passes any

## Shape

- **Three levels at most:** modules, then lessons, then (rarely) sub-lessons. Leaves are lessons. A level-2 node with children is a section that groups related lessons in a big module.
- **Modules** are coherent themes, in order: foundations first, then core features, then advanced and production topics. A module usually has 3–8 lessons.
- **Lessons:** one idea each, small enough for one focused example, big enough to be worth a chapter. "Conditional edges" is a lesson. "Graphs" is a module. "The second argument of add_edge" is a paragraph.
- **Size:** there is no fixed limit. Cover what a practitioner needs to use the technology well in real projects: the core thoroughly, important advanced features, and production concerns (testing, persistence, errors, deployment) if the sources treat them. Leave out topics that only one weak source mentions. Say in the `description` what the course covers and what it leaves out.

## Order and dependencies

- Simple to complex, guided by topic difficulty and prerequisites, and by how the structure sources order things. Deviate from the official order only for a clear teaching reason.
- `prerequisites` lists the earlier lessons a lesson relies on directly. Never point forward.
- Introduce concepts just before they are needed, not all up front.

## The example storyline

Plan which example each lesson uses. This is what makes the course feel like one piece:
- Use **a few recurring domains** that are trivially understood: a calculator, support tickets, a to-do list, a library catalog, an online order. Use one domain across a module where it fits.
- `example: {name: ticket-router, mode: extend, from: "1.2"}` means the lesson starts from lesson 1.2's code and adds the new concept. Chains of 2–4 lessons work well. Longer chains make each delta harder to see, so start a fresh example at a natural break.
- `mode: new` when the concept needs a different shape of program, or at the start of a module.
- The example names (kebab-case) are shared between lessons that use the same example.

## Lesson fields

```yaml
title: "Курс по LangGraph: от первого графа до продакшена"   # course language
description: >-                                            # course language: scope, audience, prerequisites
  …
modules:
  - id: "1"
    title: Основы LangGraph                    # course language
    slug: basics                               # English kebab-case, used in directory names
    summary: …                                 # course language, 1–2 sentences
    children:
      - id: "1.1"
        title: "Первый граф: состояние, узлы и рёбра"
        slug: hello-graph
        summary: …                             # what the lesson teaches and what the example does
        objectives:                            # course language, 2–4 observable outcomes
          - Описать состояние графа через TypedDict и понять, как узлы его обновляют
        prerequisites: []
        example: {name: calculator, mode: new}
        sources: [official-docs--docs-langchain-com--3cfc8e, …]   # 2–6 digest ids
```

- `sources`: the digests this lesson's writers should start from. Include a `code-truth` source, a `concepts` source, and a `pitfalls` source when one exists. Use ids from `codelabgen sources list --status kept --status user --brief`.
- Don't set `services` or `env`: the runtime planner adds them after you.
- `codelabgen schema show curriculum` prints the schema.

## Finish

1. `codelabgen curriculum number --course <dir>` assigns ids by position and fixes references, so you can reorder freely.
2. `codelabgen curriculum validate --course <dir>` must print `ok`.
3. Status notes: the number of modules and lessons, the main storyline, and anything you deliberately left out.

## Revising after user feedback

The orchestrator passes the user's requests. Make the smallest change that satisfies them, keep the rest stable, renumber and validate again, and list what changed in your notes.
