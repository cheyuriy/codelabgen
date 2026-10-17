"""Topic records extracted from sources: `.codelabgen/topics/<source-id>.jsonl`.

`merge` folds them into `topics/summary.md`: one row per distinct topic, with how
many sources cover it, the average difficulty and the APIs involved. That
summary is what the curriculum architect reads first.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from codelabgen import sources as srcmod
from codelabgen.course import Course, atomic_write
from codelabgen.models import Topic


class TopicsError(Exception):
    pass


def topics_dir(course: Course) -> Path:
    return course.meta / "topics"


def add(course: Course, source_id: str, rows: list[dict]) -> int:
    """Replace the topics of one source (so re-extraction never duplicates)."""
    known = {s.id for s in srcmod.load(course)}
    if source_id not in known:
        raise TopicsError(f"unknown source {source_id}; see `codelabgen sources list --brief`")
    topics = []
    for row in rows:
        topic = Topic.model_validate({"source_id": source_id} | row)
        if topic.source_id != source_id:
            raise TopicsError(
                f"topic {topic.name!r} has source_id {topic.source_id}, expected {source_id}"
            )
        topics.append(topic)
    text = "".join(t.model_dump_json() + "\n" for t in topics)
    atomic_write(topics_dir(course) / f"{source_id}.jsonl", text)
    return len(topics)


def load(course: Course) -> list[Topic]:
    folder = topics_dir(course)
    if not folder.is_dir():
        return []
    return [
        Topic.model_validate_json(line)
        for path in sorted(folder.glob("*.jsonl"))
        for line in path.read_text().splitlines()
        if line.strip()
    ]


def key(name: str) -> str:
    """Normalized topic name for exact-match merging."""
    name = name.casefold().replace("ё", "е")
    name = re.sub(r"[`'\"()\[\]]", "", name)
    return re.sub(r"[\s_\-/.]+", "", name)  # "StateGraph" == "state graph" == "state-graph"


@dataclass
class MergedTopic:
    name: str
    summaries: list[str] = field(default_factory=list)
    sources: set[str] = field(default_factory=set)
    difficulties: list[int] = field(default_factory=list)
    apis: set[str] = field(default_factory=set)
    prerequisites: set[str] = field(default_factory=set)

    @property
    def difficulty(self) -> float:
        return sum(self.difficulties) / len(self.difficulties)


def merge(course: Course) -> tuple[list[MergedTopic], Path]:
    merged: dict[str, MergedTopic] = {}
    rank = {s.id: i for i, s in enumerate(srcmod.load(course))}  # registry order: docs first
    spellings: dict[str, dict[str, tuple[int, int]]] = defaultdict(dict)
    for topic in load(course):
        k = key(topic.name)
        count, best = spellings[k].get(topic.name, (0, len(rank)))
        spellings[k][topic.name] = (count + 1, min(best, rank.get(topic.source_id, len(rank))))
        item = merged.setdefault(k, MergedTopic(topic.name))
        item.summaries.append(topic.summary)
        item.sources.add(topic.source_id)
        item.difficulties.append(topic.difficulty)
        item.apis.update(topic.apis)
        item.prerequisites.update(topic.prerequisites)
    for k, item in merged.items():
        # Most common spelling; ties go to the spelling from the most authoritative source.
        item.name = min(spellings[k].items(), key=lambda kv: (-kv[1][0], kv[1][1]))[0]
    items = sorted(merged.values(), key=lambda t: (round(t.difficulty), -len(t.sources), t.name))

    roles = {s.id: s.roles for s in srcmod.load(course)}
    lines = [
        "# Topics found in the sources",
        "",
        f"{len(items)} distinct topics (exact-name merge; similar names are not merged) from "
        f"{len({t.source_id for t in load(course)})} sources. Sorted by difficulty, then by "
        "how many sources cover the topic.",
        "",
        "| Topic | Difficulty | Sources | Structure sources | APIs | Prerequisites |",
        "|---|---|---|---|---|---|",
    ]
    for item in items:
        structure = sum(1 for s in item.sources if "structure" in roles.get(s, []))
        apis = ", ".join(sorted(item.apis))[:120]
        prerequisites = ", ".join(sorted(item.prerequisites))[:120]
        lines.append(
            f"| {item.name} | {item.difficulty:.1f} | {len(item.sources)} | {structure} | "
            f"{apis} | {prerequisites} |"
        )
    lines += ["", "## Summaries", ""]
    for item in items:
        lines.append(f"- **{item.name}** ({', '.join(sorted(item.sources))}): {item.summaries[0]}")
    path = topics_dir(course) / "summary.md"
    atomic_write(path, "\n".join(lines) + "\n")
    return items, path
