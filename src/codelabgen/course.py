"""Locating a course directory and the files inside its `.codelabgen/`."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel

from codelabgen.models import Config

META_DIR = ".codelabgen"
COURSE_ENV = "CODELABGEN_COURSE"


class CourseNotFound(Exception):
    pass


@dataclass(frozen=True)
class Course:
    root: Path

    @property
    def meta(self) -> Path:
        return self.root / META_DIR

    @property
    def config_path(self) -> Path:
        return self.meta / "config.yaml"

    @property
    def state_path(self) -> Path:
        return self.meta / "state.json"

    @property
    def lock_path(self) -> Path:
        return self.meta / "state.lock"

    @property
    def events_path(self) -> Path:
        return self.meta / "events.jsonl"

    def load_config(self) -> Config:
        return Config.model_validate(yaml.safe_load(self.config_path.read_text()))

    def save_config(self, config: Config) -> None:
        data = config.model_dump(mode="json", exclude_none=True)
        atomic_write(self.config_path, yaml.safe_dump(data, sort_keys=False, allow_unicode=True))

    @classmethod
    def find(cls, explicit: str | Path | None = None) -> Course:
        """Resolve the course from an explicit path, $CODELABGEN_COURSE, or the cwd upwards."""
        start = explicit or os.environ.get(COURSE_ENV)
        if start:
            root = Path(start).expanduser().resolve()
            if not (root / META_DIR / "config.yaml").is_file():
                raise CourseNotFound(
                    f"{root} is not a codelabgen course (no {META_DIR}/config.yaml)"
                )
            return cls(root)
        here = Path.cwd().resolve()
        for candidate in (here, *here.parents):
            if (candidate / META_DIR / "config.yaml").is_file():
                return cls(candidate)
        raise CourseNotFound(
            f"no codelabgen course found from {here}; pass --course or set {COURSE_ENV}"
        )


def atomic_write(path: Path, text: str) -> None:
    """Write via a temp file in the same directory, then rename over the target."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def dump_json(model: BaseModel) -> str:
    return json.dumps(model.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"
