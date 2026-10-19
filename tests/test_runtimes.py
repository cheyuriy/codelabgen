"""Runtimes: layout, stubs, extend-copy and commands for python-uv, node and go.

Tests that run real toolchains are skipped when node or go is not installed.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from codelabgen import curriculum as cur
from codelabgen import runtimes, toc
from codelabgen.init import init_course
from codelabgen.scaffold import scaffold_course, scaffold_lesson
from codelabgen.verify import verify

FIXTURE = Path(__file__).parent / "fixtures" / "langgraph-curriculum.yaml"


def make_course(tmp_path, kind):
    course = init_course(tmp_path / kind, topic="T", language="en")
    data = yaml.safe_load(FIXTURE.read_text())
    data["modules"][0]["children"][2]["services"] = []
    (course.meta / "curriculum.yaml").write_text(yaml.safe_dump(data, allow_unicode=True))
    config = course.load_config()
    config.runtime.kind = kind
    course.save_config(config)
    scaffold_course(course)
    return course


def lesson(course, lesson_id):
    return cur.find_lesson(cur.load(course), lesson_id)


def write_spec(course, lesson_id, run_cmd):
    path = course.meta / "lessons" / lesson_id / "spec.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {"id": lesson_id, "title": "t", "scenario": "s", "files": [], "run_cmd": run_cmd}
        )
    )


@pytest.mark.parametrize(
    ("kind", "files"),
    [
        (
            "python-uv",
            [
                "ruff.toml",
                "1-basics/pyproject.toml",
                "1-basics/1.2-routing/src/l1_2_routing/__init__.py",
            ],
        ),
        (
            "node",
            [
                "biome.json",
                "1-basics/package.json",
                "1-basics/tsconfig.base.json",
                "1-basics/1.2-routing/package.json",
                "1-basics/1.2-routing/src/main.ts",
            ],
        ),
        ("go", ["1-basics/go.work", "1-basics/1.2-routing/go.mod", "1-basics/1.2-routing/main.go"]),
    ],
)
def test_scaffold_layout(tmp_path, kind, files):
    course = make_course(tmp_path, kind)
    for name in files:
        assert (course.root / name).is_file(), name
    gitignore = (course.root / ".gitignore").read_text()
    assert ("node_modules/" in gitignore) == (kind == "node")
    assert ".codelabgen/" in gitignore.splitlines()
    runtime = runtimes.get(kind)
    item = lesson(course, "1.2")
    assert runtimes.is_stub(runtime, course.root / item.rel_dir, item)
    assert runtimes.real_code_files(runtime, course.root / item.rel_dir, item) == []


def test_node_files():
    runtime = runtimes.get("node")
    module = json.loads(
        runtime.module_files(
            cur.CurriculumNode(id="1", title="M", slug="m", summary="s"), ["1.1-a"]
        )["package.json"]
    )
    assert module["workspaces"] == ["1.1-a"] and module["devDependencies"]["vitest"]
    assert (
        json.loads(
            runtime.module_files(cur.CurriculumNode(id="1", title="M", slug="m", summary="s"), [])[
                "tsconfig.base.json"
            ]
        )["compilerOptions"]["allowImportingTsExtensions"]
        is True
    )


def test_go_copy_renames_module_path(tmp_path):
    course = make_course(tmp_path, "go")
    source = course.root / lesson(course, "1.2").rel_dir
    (source / "main.go").write_text('package main\n\nimport "codelab.local/l1_2_routing/queue"\n')
    (source / "queue").mkdir()
    (source / "queue" / "queue.go").write_text("package queue\n")
    assert scaffold_lesson(course, "1.3").copied_from == {"1.3": "1.2"}
    target = course.root / lesson(course, "1.3").rel_dir
    assert (target / "go.mod").read_text().startswith("module codelab.local/l1_3_persistence\n")
    assert "codelab.local/l1_3_persistence/queue" in (target / "main.go").read_text()
    assert (target / "queue" / "queue.go").is_file()


def test_node_copy_renames_package(tmp_path):
    course = make_course(tmp_path, "node")
    source = course.root / lesson(course, "1.2").rel_dir
    (source / "src" / "router.ts").write_text("export const x = 1;\n")
    scaffold_lesson(course, "1.3")
    target = course.root / lesson(course, "1.3").rel_dir
    assert json.loads((target / "package.json").read_text())["name"] == "l1-3-persistence"
    assert (target / "src" / "router.ts").is_file()
    assert not (target / "node_modules").exists()


@pytest.mark.parametrize(
    ("kind", "sync", "run"),
    [
        (
            "python-uv",
            "cd 1-basics && uv sync --all-packages --quiet",
            "uv run --package l1-2-routing python -m l1_2_routing",
        ),
        ("node", "cd 1-basics && npm install --no-audit --no-fund --silent", "npx tsx src/main.ts"),
        ("go", "cd 1-basics/1.2-routing && go mod download", "go run ."),
    ],
)
def test_readme_and_run_sh_commands(tmp_path, kind, sync, run):
    course = make_course(tmp_path, kind)
    toc.generate(course)
    readme = (course.root / lesson(course, "1.2").rel_dir / "README.md").read_text()
    assert sync in readme and run in readme
    listed = subprocess.run(
        [str(course.root / "run.sh"), "list"], capture_output=True, text=True, check=True
    )
    assert "1.2" in listed.stdout


def test_unknown_runtime():
    with pytest.raises(runtimes.UnknownRuntime, match="supported: python-uv, node, go"):
        runtimes.get("ruby")


# --- with real toolchains ------------------------------------------------------------------


@pytest.mark.skipif(not shutil.which("go"), reason="go is not installed")
def test_go_verify_end_to_end(tmp_path):
    course = make_course(tmp_path, "go")
    folder = course.root / lesson(course, "1.1").rel_dir
    (folder / "main.go").write_text(
        'package main\n\nimport "fmt"\n\nfunc main() {\n\tfmt.Println(Add(2, 3))\n}\n'
    )
    (folder / "add.go").write_text(
        "package main\n\n// Add adds.\nfunc Add(a, b int) int {\n\treturn a + b\n}\n"
    )
    (folder / "add_test.go").write_text(
        'package main\n\nimport "testing"\n\n'
        "func TestAdd(t *testing.T) {\n\tif Add(2, 3) != 5 {\n"
        '\t\tt.Fatal("bad")\n\t}\n}\n'
    )
    write_spec(course, "1.1", "go run .")
    result = verify(course, "1.1")
    assert result.passed, result.failed_step


@pytest.mark.skipif(not shutil.which("npm"), reason="node is not installed")
def test_node_verify_end_to_end(tmp_path):
    course = make_course(tmp_path, "node")
    folder = course.root / lesson(course, "1.1").rel_dir
    (folder / "src" / "add.ts").write_text(
        "export function add(a: number, b: number): number {\n  return a + b;\n}\n"
    )
    (folder / "src" / "main.ts").write_text(
        'import { add } from "./add.ts";\n\nconsole.log(add(2, 3));\n'
    )
    (folder / "tests" / "add.test.ts").write_text(
        'import { expect, test } from "vitest";\nimport { add } from "../src/add.ts";\n\n'
        'test("add", () => {\n  expect(add(2, 3)).toBe(5);\n});\n'
    )
    write_spec(course, "1.1", "npx tsx src/main.ts")
    result = verify(course, "1.1")
    assert result.passed, result.failed_step
