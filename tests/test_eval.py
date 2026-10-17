"""The evaluation rubric on a small scaffolded course."""

import shutil
from pathlib import Path

import pytest

from codelabgen import evaluate
from codelabgen.init import init_course
from codelabgen.models import Phase, Stage
from codelabgen.scaffold import scaffold_course
from codelabgen.state import StateStore

FIXTURE = Path(__file__).parent / "fixtures" / "langgraph-curriculum.yaml"

READALONG = """# Разбор

<!-- snippet: src/l1_1_hello_graph/graph.py#a -->
<!-- /snippet -->

<!-- snippet: src/l1_1_hello_graph/graph.py#b -->
<!-- /snippet -->

```text
{'total': 5}
```

1. one <details><summary>?</summary>x</details>
2. two <details><summary>?</summary>x</details>
3. three <details><summary>?</summary>x</details>
"""

NOTES = """# Notes

## Problem
## Concept
## How it works

```mermaid
flowchart LR
  A --> B
```

## Self-check

<details><summary>Q</summary>A</details>

## Further reading

- [Docs](https://docs.example.com/a)
- [Blog](https://blog.example.com/b)
"""


@pytest.fixture
def course(tmp_path):
    course = init_course(tmp_path / "course", topic="LangGraph", language="ru")
    shutil.copy(FIXTURE, course.meta / "curriculum.yaml")
    store = StateStore(course)
    for phase in list(Phase)[1:8]:
        current = store.load().phase
        store.advance_phase(phase, approved=current in (Phase.GATE_SOURCES, Phase.GATE_PLAN))
    scaffold_course(course)
    store.advance_phase(Phase.LESSONS)
    return course


def complete_lesson_1_1(course):
    folder = course.root / "1-basics/1.1-hello-graph"
    (folder / "src/l1_1_hello_graph/graph.py").write_text(
        '"""Graph."""\n\n# region a\n# A comment.\ndef f():\n    return 1\n# endregion\n'
        "# region b\ndef g():\n    return 2\n# endregion\n"
    )
    (folder / "tests/test_graph.py").write_text(
        "def test_a():\n    pass\n\n\ndef test_b():\n    pass\n"
    )
    (folder / "docs/readalong.md").write_text(READALONG)
    (folder / "docs/notes.md").write_text(NOTES)
    store = StateStore(course)
    for stage in list(Stage)[1:8]:
        store.set_stage("1.1", stage)


def test_content_criteria(course):
    complete_lesson_1_1(course)
    result = evaluate.evaluate(course)
    content = result["details"]["content"]
    assert content["1.1"]["score"] == 100, content["1.1"]["missing"]
    assert content["1.2"]["score"] < 20 and "readalong exists" in content["1.2"]["missing"]
    assert result["details"]["completion"] == {"done": 1, "total": 3, "blocked": []}
    assert result["dimensions"]["verification"] == 0  # no verify runs yet
    assert 0 < result["overall"] < 60
    assert (course.meta / "eval.md").read_text().startswith("# Evaluation: LangGraph")


def test_human_template_and_scores(course):
    complete_lesson_1_1(course)
    evaluate.evaluate(course)
    path = evaluate.human_path(course)
    text = path.read_text()
    assert "## 1.1 " in text and text.count("- [_]") == 12
    path.write_text(text.replace("- [_]", "- [4]", 6))
    human = evaluate.evaluate(course)["human"]
    assert human == {"lessons": {"1.1": {q: 4 for q in evaluate.HUMAN_QUESTIONS}}, "average": 4.0}


def test_blocked_lessons_cost_completion(course):
    StateStore(course).block("1.2", reason="needs a key")
    result = evaluate.evaluate(course)
    assert result["details"]["completion"]["blocked"] == ["1.2"]
    assert result["dimensions"]["completion"] == 0
