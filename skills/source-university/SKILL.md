---
name: source-university
description: How to find university course pages, syllabi, lecture notes and assignments that cover a technology or its underlying concepts, for a codelabgen course. Source type `university`.
user-invocable: false
---

# University material (`university`)

University courses are carefully sequenced and explain fundamentals well. A specific framework is rarely a whole course, but it often appears as a module, a lab or an assignment, and the concepts underneath it (distributed systems, compilers, agents, databases) are taught everywhere.

## Search

- WebSearch: `<topic> course syllabus`, `<topic> lecture notes`, `<topic> lab assignment`, `site:edu <topic>`, `site:ac.uk <topic>`, and in Russian `<topic> курс лекции`, `site:*.ru <topic> лекция`.
- Look for the technology itself and for its **core concept**: "agent orchestration", "stateful workflows", "graph-based execution" for LangGraph.
- Known sources of open course material: MIT OpenCourseWare, Stanford (CS courses publish their syllabi), CMU, Berkeley, ETH, and for Russian-language material ITMO, HSE, MIPT.

## What to record

- **Syllabi and schedules** that place the topic in a sequence (`structure`). In `reason`, say which weeks or lectures cover it.
- **Lecture notes or slides** with clear explanations of the underlying concepts (`concepts`).
- **Labs and assignments** using the technology (`code-truth` if on the pinned version, `structure` otherwise).

It is normal to find little for a young framework. Then record 1–3 strong items on the underlying concepts and say so in your status notes. Don't pad the list.
