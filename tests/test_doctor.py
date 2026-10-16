import sys

from codelabgen import doctor
from codelabgen.doctor import Tool, check_tools


def test_probe_failure_marks_tool_unusable(monkeypatch):
    fail = Tool(
        "python", "x", version_args=("-V",), probe_args=("-c", "raise SystemExit('no daemon')")
    )
    ok = Tool("python", "x", version_args=("-V",), probe_args=("-c", "pass"))
    monkeypatch.setattr(doctor, "TOOLS", [fail, ok])
    monkeypatch.setattr(doctor.shutil, "which", lambda _: sys.executable)
    failed, passed = check_tools()
    assert failed.path and not failed.usable and failed.problem == "no daemon"
    assert passed.usable and passed.version.startswith("Python")


def test_missing_tool(monkeypatch):
    monkeypatch.setattr(doctor, "TOOLS", [Tool("nope", "x")])
    monkeypatch.setattr(doctor.shutil, "which", lambda _: None)
    (status,) = check_tools()
    assert not status.usable and status.path is None
