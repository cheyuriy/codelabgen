"""Hook handlers: the state-file guard and the subagent logger."""

import json

from codelabgen import hooks
from codelabgen.init import init_course


def test_guard_blocks_state_files_only(capsys):
    blocked = {"tool_input": {"file_path": "/c/.codelabgen/state.json"}}
    assert hooks.pre_tool_use(blocked) == 2
    assert "codelabgen state" in capsys.readouterr().err
    for path in ("/c/.codelabgen/curriculum.yaml", "/c/state.json", "/c/1-basics/x/README.md"):
        assert hooks.pre_tool_use({"tool_input": {"file_path": path}}) == 0
    assert hooks.pre_tool_use({}) == 0


def test_subagent_stop_logs_when_a_course_is_found(tmp_path, monkeypatch):
    monkeypatch.delenv("CODELABGEN_COURSE", raising=False)
    course = init_course(tmp_path / "course", topic="T")
    nested = course.root / "1-basics"
    nested.mkdir()
    assert hooks.subagent_stop({"cwd": str(nested), "agent_type": "plugin:codelabgen:x"}) == 0
    last = json.loads(course.events_path.read_text().splitlines()[-1])
    assert last["kind"] == "subagent-stop" and last["data"]["agent_type"] == "plugin:codelabgen:x"
    assert hooks.subagent_stop({"cwd": str(tmp_path / "elsewhere")}) == 0  # no course: no-op
