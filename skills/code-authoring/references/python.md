# Python lessons (`python-uv`)

## Layout

```
<module dir>/                       # uv workspace: one .venv and uv.lock for the module
└── <lesson dir>/
    ├── pyproject.toml              # project <project>, its pinned dependencies
    ├── src/<package>/
    │   ├── __init__.py             # one-line docstring
    │   ├── __main__.py             # the live run: `python -m <package>`
    │   └── *.py                    # the lesson code
    └── tests/test_*.py             # offline tests (pytest, plain asserts)
```

Import the lesson's own modules by the package name: `from l1_2_routing.graph import build_graph`.

## Dependencies

- Add them to `dependencies` in the lesson's `pyproject.toml`, **pinned exactly** to the course's version: `"langgraph==1.2.15"`. Pin extras (`langgraph-checkpoint-postgres`, `psycopg[binary]`) to versions that work with it.
- Sync the module's workspace in the module directory: `env -u VIRTUAL_ENV uv sync --all-packages`. Lessons in one module share a lockfile, so keep versions consistent with the other lessons.
- `pytest` and `ruff` come from the module's dev group; don't add them.

## Installed sources

`<module dir>/.venv/lib/python3.*/site-packages/<package>/`.

## Style

- Docstrings on every function and class, type hints on functions and state definitions.
- Environment: `os.environ["NAME"]`, or `os.environ.get("NAME", "default")` for non-secrets.
- Format and lint in the lesson directory: `env -u VIRTUAL_ENV uv run ruff format .` and `env -u VIRTUAL_ENV uv run ruff check --fix .`
- `ruff format` puts two blank lines before an `# endregion` that follows a top-level function or class. That's expected.

## Tests and run

- Tests: `tests/test_*.py`. Verify runs `pytest -q tests`.
- Live run: `run_cmd` is usually `python -m <package>`, run through `uv run --package <project>`.
- Fake LLMs for tests: `langchain_core.language_models.fake_chat_models.GenericFakeChatModel`, or a small stub class.
