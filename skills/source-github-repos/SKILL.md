---
name: source-github-repos
description: How to find popular, well-maintained repositories that use a technology — awesome lists, real projects, starter templates — via GitHub repository and code search, for a codelabgen course. Source type `github-repo`.
user-invocable: false
---

# Repositories that use the technology (`github-repo`)

Real projects show how people actually structure code with the technology: which features they use, in which combinations, at what scale. The technology's own repo is covered by `package-internals`; this hunter looks at everyone else.

## Search

- **Awesome lists:** `codelabgen github repos "awesome <topic>"`. A good list is a source itself (`structure`), and a map to more repos.
- **By name and topic:** `codelabgen github repos "<topic> in:name,description,readme" --sort stars`, or with GitHub topics: `topic:<topic>`.
- **Who depends on it:** code search in dependency files, for example `codelabgen github code '"langgraph" filename:pyproject.toml'` or `'"@langchain/langgraph" filename:package.json'`. This finds real projects that keyword search misses. Code search allows 10 requests per minute: make each query count.
- **Official orgs:** the maintainers' other repos (starter templates, example apps): `codelabgen github repos "org:<org>"`.

## Check each candidate

`codelabgen github meta <repo…>` gives stars, last push, license, archived status and topics. Then fetch the README (`codelabgen fetch https://github.com/<repo>`) and look at the dependency file.
- **Recent:** pushed within the last year and not archived.
- **On the pinned major version:** check the dependency file.
- **Readable:** a clear README and a sensible structure. A huge monorepo is only useful if you can point at the relevant part.
- **Popularity is a hint, not proof.** A 200-star repo with clean code beats a 20k-star repo of prompt collections.

## Roles

- small, focused example apps and templates: `code-truth`
- awesome lists and tutorial repos with step-by-step folders: `structure`
- larger real-world projects: `code-truth` (how features combine). Name the interesting paths in `reason`.

Stars, the last push date and the pinned-version check belong in `reason`, for example: "12k stars, active, langgraph 1.x: multi-agent customer support with checkpointing in src/graph/."
