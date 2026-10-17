# Python with uv (`python-uv`)

What `codelabgen scaffold` creates, and what lesson code can rely on.

## Layout

```
<course>/
├── <n>-<module-slug>/              # one uv workspace per module (runtime.per: module)
│   ├── pyproject.toml              # generated: workspace members + dev group (pytest, ruff)
│   ├── uv.lock                     # one lock for all lessons of the module
│   └── <id>-<lesson-slug>/         # a workspace member
│       ├── pyproject.toml          # project l<id>-<slug>, its own pinned dependencies
│       ├── src/l<id>_<slug>/       # the package; __main__.py is the live run
│       └── tests/
├── ruff.toml                       # lint rules for all lessons
├── docker-compose.yml              # generated from the services the lessons use
└── .env.example / .env             # course variables; a lesson may add its own .env.example
```

## Consequences for planning

- **One version per module.** Lessons in a module resolve together, so they share the pinned technology version and every common dependency. A lesson that needs a different major version must go in its own module, or the course uses `runtime.per: lesson`.
- **Python version:** `requires-python = ">=3.12"`. If the technology needs an older Python, report it.
- **Optional packages** (integrations, drivers) are added per lesson by the code author. Plan lessons so that each module's dependency set stays reasonable.
- **Offline tests:** every lesson's tests run without network, keys or services. For LLM-based examples this means fake models in the tests, such as `langchain_core.language_models.fake_chat_models.GenericFakeChatModel` or a stub class, while the live run uses the real model chosen by the user.
- **Live runs** use real services and real keys, read from the environment (`os.environ["OPENAI_API_KEY"]`, `os.environ.get("LLM_MODEL", "<default>")`).
