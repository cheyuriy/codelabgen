"""Runtimes: how lessons of one ecosystem are laid out, verified and run.

  python-uv  one uv workspace per module; ruff, pytest; `uv run`
  node       one npm workspace per module; TypeScript via tsx, Biome, tsc, vitest
  go         one go.work per module, one Go module per lesson; go vet, gofmt, go test

A lesson's names are shared by all runtimes: `lesson.package` (l1_2_routing) is
the Python package and the last part of the Go module path, `lesson.project`
(l1-2-routing) is the uv project and the npm package name. Renaming a lesson
(extend-copy, renumbering) replaces both everywhere.
"""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from codelabgen.curriculum import Lesson
from codelabgen.models import CurriculumNode

# Directories never copied, scanned or treated as lesson code.
CACHE_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache", ".venv", "node_modules", "dist"}
NOT_CODE = {"docs", "README.md", ".env", ".env.example"} | CACHE_DIRS


class UnknownRuntime(Exception):
    pass


@dataclass(frozen=True)
class StepSpec:
    name: str
    argv: list[str]
    cwd: str  # "lesson" or "module"
    timeout: int


@dataclass(frozen=True)
class ShellCommands:
    """Commands for run.sh and the lesson README."""

    sync: str
    sync_cwd: str  # "module" or "lesson"
    run: str
    test: str


class Runtime:
    kind = ""
    tools: tuple[str, ...] = ()
    gitignore: tuple[str, ...] = ()

    # --- files ---------------------------------------------------------------------
    def course_files(self) -> dict[str, str]:
        return {}

    def module_files(self, module: CurriculumNode, members: list[str]) -> dict[str, str]:
        return {}

    def lesson_files(self, lesson: Lesson) -> dict[str, str]:
        """Created when missing; never overwritten (the code author owns them)."""
        raise NotImplementedError

    def stub_files(self, lesson: Lesson) -> dict[str, str]:
        """The placeholder code files among lesson_files."""
        raise NotImplementedError

    def path_renames(self, source: Lesson, target: Lesson) -> list[tuple[str, str]]:
        return []

    # --- code ----------------------------------------------------------------------
    def code_files(self, lesson_dir: Path, lesson: Lesson) -> list[Path]:
        raise NotImplementedError

    def test_files(self, lesson_dir: Path, lesson: Lesson) -> list[Path]:
        raise NotImplementedError

    def default_run_cmd(self, lesson: Lesson) -> str:
        raise NotImplementedError

    # --- commands ------------------------------------------------------------------
    def verify_steps(self, lesson: Lesson) -> list[StepSpec]:
        """sync, lint, format and offline-tests, in that order."""
        raise NotImplementedError

    def live_argv(self, lesson: Lesson, run_cmd: str) -> list[str]:
        return shlex.split(run_cmd)

    def shell(self, lesson: Lesson, run_cmd: str) -> ShellCommands:
        raise NotImplementedError

    def record_command(self, lesson: Lesson, cmd: str) -> tuple[str, str]:
        """(what the viewer sees typed, the real command)."""
        return cmd, cmd


def walk_files(root: Path, suffixes: tuple[str, ...]) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(
        p
        for p in root.rglob("*")
        if p.is_file() and p.suffix in suffixes and not (set(p.relative_to(root).parts) & NOT_CODE)
    )


# --- Python with uv ----------------------------------------------------------------------


class PythonUv(Runtime):
    kind = "python-uv"
    tools = ("uv",)
    gitignore = (".venv/", "__pycache__/", ".pytest_cache/", ".ruff_cache/", ".mypy_cache/")

    def course_files(self) -> dict[str, str]:
        from codelabgen.scaffold import TEMPLATES

        return {"ruff.toml": (TEMPLATES / "ruff.toml").read_text()}

    def module_files(self, module, members):
        from codelabgen.scaffold import render

        return {
            "pyproject.toml": render("module_pyproject.toml.j2", module=module, members=members)
        }

    def lesson_files(self, lesson):
        from codelabgen.scaffold import render

        return {
            "pyproject.toml": render("lesson_pyproject.toml.j2", lesson=lesson),
            **self.stub_files(lesson),
        }

    def stub_files(self, lesson):
        return {
            f"src/{lesson.package}/__init__.py": f'"""Lesson {lesson.id}: {lesson.node.title}."""\n'
        }

    def path_renames(self, source, target):
        return [(f"src/{source.package}", f"src/{target.package}")]

    def code_files(self, lesson_dir, lesson):
        return walk_files(lesson_dir / "src", (".py",))

    def test_files(self, lesson_dir, lesson):
        return [p for p in walk_files(lesson_dir / "tests", (".py",)) if p.name.startswith("test_")]

    def default_run_cmd(self, lesson):
        return f"python -m {lesson.package}"

    def verify_steps(self, lesson):
        run = ["uv", "run", "--package", lesson.project, "--frozen"]
        return [
            StepSpec("sync", ["uv", "sync", "--all-packages"], "module", 900),
            StepSpec("lint", [*run, "ruff", "check", "."], "lesson", 120),
            StepSpec("format", [*run, "ruff", "format", "--check", "."], "lesson", 120),
            StepSpec("offline-tests", [*run, "pytest", "-q", "tests"], "lesson", 600),
        ]

    def live_argv(self, lesson, run_cmd):
        return ["uv", "run", "--package", lesson.project, "--frozen", *shlex.split(run_cmd)]

    def shell(self, lesson, run_cmd):
        return ShellCommands(
            sync="uv sync --all-packages --quiet",
            sync_cwd="module",
            run=f"uv run --package {lesson.project} {run_cmd}",
            test=f"uv run --package {lesson.project} pytest -q tests",
        )

    def record_command(self, lesson, cmd):
        return f"uv run {cmd}", shlex.join(
            ["uv", "run", "--frozen", "--package", lesson.project, *shlex.split(cmd)]
        )


# --- Node with TypeScript ------------------------------------------------------------------

NODE_DEV = {
    "@biomejs/biome": "2.5.15",
    "@types/node": "24.19.2",
    "tsx": "4.23.15",
    "typescript": "7.0.2",
    "vitest": "5.0.5",
}
NODE_TSCONFIG = {
    "compilerOptions": {
        "target": "es2024",
        "module": "nodenext",
        "moduleResolution": "nodenext",
        "strict": True,
        "noEmit": True,
        "allowImportingTsExtensions": True,
        "verbatimModuleSyntax": True,
        "skipLibCheck": True,
        "types": ["node"],
    }
}
BIOME = {
    "$schema": "https://biomejs.dev/schemas/2.5.15/schema.json",
    "formatter": {"indentStyle": "space", "indentWidth": 2, "lineWidth": 100},
    "linter": {"rules": {"recommended": True}},
    "javascript": {"formatter": {"quoteStyle": "double"}},
}


def dump_json(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


class Node(Runtime):
    kind = "node"
    tools = ("node", "npm")
    gitignore = ("node_modules/", "dist/")

    def course_files(self):
        return {"biome.json": dump_json(BIOME)}

    def module_files(self, module, members):
        package = {
            "name": f"module-{module.id}-{module.slug}",
            "private": True,
            "type": "module",
            "description": f"Generated by codelabgen. Module {module.id}: {module.title}",
            "workspaces": members,
            "devDependencies": NODE_DEV,
        }
        return {"package.json": dump_json(package), "tsconfig.base.json": dump_json(NODE_TSCONFIG)}

    def lesson_files(self, lesson):
        package = {
            "name": lesson.project,
            "version": "0.1.0",
            "private": True,
            "type": "module",
            "description": f"Lesson {lesson.id}: {lesson.node.title}",
            "dependencies": {},
        }
        tsconfig = {"extends": "../tsconfig.base.json", "include": ["src", "tests"]}
        return {
            "package.json": dump_json(package),
            "tsconfig.json": dump_json(tsconfig),
            **self.stub_files(lesson),
        }

    def stub_files(self, lesson):
        return {"src/main.ts": f"// Lesson {lesson.id}: {lesson.node.title}.\n"}

    def code_files(self, lesson_dir, lesson):
        return walk_files(lesson_dir / "src", (".ts", ".tsx", ".js", ".mjs"))

    def test_files(self, lesson_dir, lesson):
        return [
            p
            for p in walk_files(lesson_dir / "tests", (".ts", ".js"))
            if ".test." in p.name or ".spec." in p.name
        ]

    def default_run_cmd(self, lesson):
        return "npx tsx src/main.ts"

    def verify_steps(self, lesson):
        npx = ["npx", "--no-install"]
        lint = (
            f"{shlex.join([*npx, 'biome', 'lint', 'src', 'tests'])} && "
            f"{shlex.join([*npx, 'tsc', '-p', 'tsconfig.json'])}"
        )
        return [
            StepSpec("sync", ["npm", "install", "--no-audit", "--no-fund"], "module", 900),
            StepSpec("lint", ["sh", "-c", lint], "lesson", 180),
            StepSpec("format", [*npx, "biome", "format", "src", "tests"], "lesson", 120),
            StepSpec("offline-tests", [*npx, "vitest", "run"], "lesson", 600),
        ]

    def shell(self, lesson, run_cmd):
        return ShellCommands(
            sync="npm install --no-audit --no-fund --silent",
            sync_cwd="module",
            run=run_cmd,
            test="npx vitest run",
        )


# --- Go ----------------------------------------------------------------------------------

GO_MODULE_HOST = "codelab.local"


def go_version() -> str:
    """The `go` directive: the installed toolchain's major.minor, else a safe default."""
    if shutil.which("go"):
        proc = subprocess.run(["go", "env", "GOVERSION"], capture_output=True, text=True)
        version = proc.stdout.strip().removeprefix("go")
        parts = version.split(".")
        if len(parts) >= 2 and parts[0].isdigit():
            return f"{parts[0]}.{parts[1]}"
    return "1.24"


class Go(Runtime):
    kind = "go"
    tools = ("go",)

    def module_files(self, module, members):
        uses = "\n".join(f"\t./{member}" for member in members)
        return {"go.work": f"go {go_version()}\n\nuse (\n{uses}\n)\n"}

    def lesson_files(self, lesson):
        return {
            "go.mod": f"module {self.module_path(lesson)}\n\ngo {go_version()}\n",
            **self.stub_files(lesson),
        }

    def stub_files(self, lesson):
        return {
            "main.go": f"// Lesson {lesson.id}: {lesson.node.title}.\npackage main\n\n"
            "func main() {}\n"
        }

    @staticmethod
    def module_path(lesson: Lesson) -> str:
        return f"{GO_MODULE_HOST}/{lesson.package}"

    def code_files(self, lesson_dir, lesson):
        return [p for p in walk_files(lesson_dir, (".go",)) if not p.name.endswith("_test.go")]

    def test_files(self, lesson_dir, lesson):
        return [p for p in walk_files(lesson_dir, (".go",)) if p.name.endswith("_test.go")]

    def default_run_cmd(self, lesson):
        return "go run ."

    def verify_steps(self, lesson):
        gofmt = (
            'files=$(gofmt -l .); if [ -n "$files" ]; then '
            'echo "not formatted (run gofmt -w .):"; echo "$files"; exit 1; fi'
        )
        return [
            StepSpec("sync", ["go", "mod", "tidy"], "lesson", 900),
            StepSpec("lint", ["go", "vet", "./..."], "lesson", 300),
            StepSpec("format", ["sh", "-c", gofmt], "lesson", 60),
            StepSpec("offline-tests", ["go", "test", "./..."], "lesson", 600),
        ]

    def shell(self, lesson, run_cmd):
        return ShellCommands(
            sync="go mod download", sync_cwd="lesson", run=run_cmd, test="go test ./..."
        )


RUNTIMES: dict[str, Runtime] = {r.kind: r for r in (PythonUv(), Node(), Go())}


def get(kind: str | None) -> Runtime:
    runtime = RUNTIMES.get(kind or "python-uv")
    if runtime is None:
        raise UnknownRuntime(f"unknown runtime {kind!r}; supported: {', '.join(RUNTIMES)}")
    return runtime


def for_course(course) -> Runtime:
    return get(course.load_config().runtime.kind)


def is_stub(runtime: Runtime, lesson_dir: Path, lesson: Lesson) -> bool:
    """True while the lesson's code is only the scaffolded placeholder (or missing)."""
    stubs = runtime.stub_files(lesson)
    code = runtime.code_files(lesson_dir, lesson)
    actual = {p.relative_to(lesson_dir).as_posix(): p for p in code}
    if not actual:
        return True
    return set(actual) == set(stubs) and all(
        actual[path].read_text() == content for path, content in stubs.items()
    )


def real_code_files(runtime: Runtime, lesson_dir: Path, lesson: Lesson) -> list[Path]:
    """Lesson code files other than the untouched placeholders."""
    stubs = runtime.stub_files(lesson)
    result = []
    for path in runtime.code_files(lesson_dir, lesson):
        rel = path.relative_to(lesson_dir).as_posix()
        if rel in stubs and path.read_text() == stubs[rel]:
            continue
        if path.name == "__init__.py" and not path.read_text().strip().strip('"').strip():
            continue
        result.append(path)
    return result
