---
name: source-official-docs
description: How to find and map a technology's official documentation for a codelabgen course — docs site, version-specific docs, guides, tutorials, API reference, best practices, and LLM-oriented docs (llms.txt). Source type `official-docs`.
user-invocable: false
---

# Official documentation (`official-docs`)

The official docs are the backbone of the course: the main source of `code-truth` and `concepts`, and often of `structure` (the order the maintainers teach things in). Find them first, map them, and record the sections that matter.

## Find the docs for the pinned version

1. Start from `research/overview.md` (docs and homepage URLs) and `codelabgen pkg-info` (registry links).
2. Find out how the site handles versions: a version switcher, `/v1/` or `/latest/` paths, or separate sites per major version. Make sure you record pages for the **pinned** major version, not an older one that search engines still rank higher.
3. Run `codelabgen llms-txt <docs root>`. When `llms.txt` exists, it is the best map of the docs: a curated list of pages. `llms-full.txt` is the whole site in one file; grep it, don't read it.

## Map the docs

Fetch the landing page and the navigation (the sidebar usually appears in the fetched Markdown or in `llms.txt`). Identify:
- **Getting started / quickstart / tutorials:** the maintainers' intended learning order (`structure`, `code-truth`)
- **Concepts / guides / how-to:** explanations of each concept (`concepts`, `code-truth`)
- **API reference:** exact signatures (`code-truth`). Record its root, not every page.
- **Best practices, production, troubleshooting, FAQ** (`pitfalls`, `concepts`)
- **Migration guides** belong to `release-notes`; leave them to that hunter.

## What to record

Record **sections**, not every page: a section landing page whose subpages cover one area, such as "Persistence" or "Graph API". Aim for the pages a teacher would hand out. Typically:
- the docs root or `llms.txt` (`structure`)
- the tutorial sequence (`structure`, `code-truth`)
- 3–6 concept or guide sections central to the technology (`concepts`, `code-truth`)
- the API reference root (`code-truth`)
- best practices or troubleshooting, if they exist (`pitfalls`)

Official docs score high (0.85–1.0) when they match the pinned version. Pages for an older major version score low, or aren't recorded at all.
