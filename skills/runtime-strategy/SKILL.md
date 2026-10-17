---
name: runtime-strategy
description: How a codelabgen course's examples run — choosing the runtime and project layout, the Docker services each lesson needs, and the external services (LLM APIs, cloud accounts) and environment variables the user must provide. Used by the runtime planner after the curriculum is drafted.
user-invocable: false
---

# Planning how the examples run

Every lesson must install, run and pass its tests on the user's machine with one command (`./run.sh <id>`). The runtime planner decides the setup that makes this possible, and finds out what the user has to provide: accounts, API keys, choices of provider.

## 1. Runtime

| Ecosystem | Supported | Reference |
|---|---|---|
| Python | yes: `python-uv` | `references/python-uv.md` |
| Anything else | not yet | Report `needs-user`: codelabgen can only scaffold and verify Python courses so far |

Set it: `codelabgen config set runtime.kind python-uv --course <dir>`.

Layout, `runtime.per`:
- `module` (default): one uv workspace per module. Lessons share one lockfile, so they share dependency versions. This is right when the course pins one version of the technology.
- `lesson`: only when lessons in one module truly need conflicting versions (rare; for example a lesson comparing two major versions).

## 2. Services (Docker Compose)

Read each lesson's summary and objectives and ask what infrastructure its example needs to be real: a database for persistence, a cache, a queue, a vector store. Prefer the simplest option that still teaches the concept. For example, the lesson on persistence uses Postgres, but lessons that only need some memory use the in-memory backend.

- Add `services: [postgres]` to the lesson nodes in `.codelabgen/curriculum.yaml`.
- Built-in services: `postgres` (`POSTGRES_URL`), `redis` (`REDIS_URL`). For anything else, define it in `.codelabgen/services.yaml` (`references/docker-services.md`).
- Offline tests never need services. Only the live run uses them.

## 3. External services and keys

Find every lesson whose example would naturally call an external API: an LLM, embeddings, a search API, a cloud service, a SaaS product.

- **Don't choose the provider.** The user chooses at the plan review. Your job is to list the options and the questions.
- Prefer designs that need **fewer** keys. One LLM provider for the whole course is better than three. A local alternative (Ollama, a local embedding model) is worth offering when it works well enough.
- Lessons whose concept doesn't need the external service should not use it. Rule-based or fake components often teach the mechanism better.

Write `.codelabgen/research/runtime.md`:

```markdown
# Runtime plan

## Runtime
python-uv, one workspace per module. Why.

## Services
| Service | Lessons | Why |
|---|---|---|
| postgres | 3.2, 3.3 | checkpointer persistence across runs |

## External services
| Need | Lessons | Options |
|---|---|---|
| Chat LLM with tool calling | 2.1–2.4, 3.x, 4.x | OpenAI (gpt-…), Anthropic (claude-…), local via Ollama (llama…, weaker tool calling) |

## Questions for the user
1. Which LLM provider and model should the examples use? (default suggestion: …)
2. …

## Environment variables (after the user answers)
For each: name, what it is, where to get it, secret or not, which lessons need it.
```

Then add the variables that don't depend on the user's answers to `env` in `curriculum.yaml`. The orchestrator adds the provider-specific ones after the user answers. Use names like `OPENAI_API_KEY` (secret, no default) and `LLM_MODEL` (not secret, with a default), so that switching providers or models means changing `.env`, not code.

## Finish

`codelabgen curriculum validate` must print `ok`. In the status notes: the runtime, the services, and the number of questions for the user.
