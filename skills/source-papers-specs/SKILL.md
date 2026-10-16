---
name: source-papers-specs
description: How to find the specifications, RFCs, design documents, ADRs, PEPs and research papers behind a technology for a codelabgen course — the "why" and the precise definitions. Source type `paper-spec`.
user-invocable: false
---

# Specifications and papers (`paper-spec`)

Many technologies rest on a specification or an idea from a paper: a protocol RFC, a language PEP, a design doc, the paper that introduced an algorithm. These give the notes depth: precise definitions and the reasoning behind the design. The role is `concepts`.

## Where to look

- **Specifications the technology implements:** RFCs, W3C/WHATWG specs, protocol specs (often linked from the docs' "concepts" or "architecture" pages).
- **Design documents and ADRs** in the repo (`docs/design`, `adr/`, `rfcs/`, `proposals/`) or on the maintainers' blog. Clone with `codelabgen repo clone` and look.
- **Language-level proposals:** PEPs, TC39 proposals, Go design docs, Rust RFCs, when the technology is a language feature or relies on one.
- **Research papers** that introduced or inspired the core ideas. Search arXiv and Semantic Scholar (`<concept> paper`, `site:arxiv.org <concept>`). For LangGraph, for example, papers on agent loops (ReAct) and on the Pregel / bulk-synchronous-parallel model behind its supersteps.

## Reading them

`codelabgen fetch <url>` handles PDFs and resolves arXiv abstract pages to the PDF. Papers are long: grep the cached text for the abstract, the definitions and the key figures, and read those parts. Don't read the whole paper.

## What to record

Record only documents that explain something the course will actually teach. In `reason`, say what to take from the document: "Defines the superstep model (Pregel, 2010) that LangGraph's execution follows: read, compute, write barrier." Original papers keep their date, and age is no penalty when the idea still holds. Score by relevance and clarity.
