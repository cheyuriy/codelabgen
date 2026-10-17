"""Sources registry, review sheet, conversions and helpers (no network)."""

import pytest

from codelabgen import fetch, research
from codelabgen import sources as src
from codelabgen.init import init_course


@pytest.fixture
def course(tmp_path):
    return init_course(tmp_path / "course", topic="LangGraph", language="ru", version="1.2.15")


def row(url, type_="article", score=0.7, **extra):
    return {
        "url": url,
        "type": type_,
        "roles": ["concepts"],
        "title": f"T {url}",
        "score": score,
        "reason": "useful",
    } | extra


# --- registry -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "normalized"),
    [
        ("https://WWW.Example.com/a/?utm_source=x&b=2#frag", "https://example.com/a?b=2"),
        (
            "https://github.com/langchain-ai/langgraph.git",
            "https://github.com/langchain-ai/langgraph",
        ),
        ("https://docs.x.dev/guide/", "https://docs.x.dev/guide"),
    ],
)
def test_normalize_url(url, normalized):
    assert src.normalize_url(url) == normalized


def test_add_assigns_ids_and_merges_duplicates(course):
    report = src.add(course, [row("https://ex.com/a"), row("https://docs.x.dev", "official-docs")])
    assert len(report.added) == 2 and report.added[0].startswith("article--ex-com--")
    again = src.add(
        course,
        [row("https://www.ex.com/a/?utm_medium=y", score=0.9, roles=["pitfalls"], reason="better")],
    )
    assert again.added == [] and again.merged == report.added[:1]
    merged = next(s for s in src.load(course) if s.type == "article")
    assert merged.roles == ["concepts", "pitfalls"] and merged.score == 0.9
    assert [s.type for s in src.load(course)] == ["official-docs", "article"]  # type order


def test_add_validates(course):
    with pytest.raises(ValueError):
        src.add(course, [row("https://ex.com", type_="blogpost")])
    with pytest.raises(ValueError):
        src.add(course, [row("https://ex.com", roles=[])])


def test_render_and_apply_round_trip(course):
    src.add(
        course,
        [
            row("https://ex.com/good", score=0.8),
            row("https://ex.com/weak", score=0.3),
            row("https://docs.x.dev", "official-docs", score=0.95),
        ],
    )
    text = src.render(course).read_text()
    assert text.startswith("# Источники: LangGraph 1.2.15")
    assert "- [x] [T https://ex.com/good]" in text and "- [ ] [T https://ex.com/weak]" in text
    assert "## Добавить свои источники" in text

    # The user drops the good article, keeps the weak one, adds two of their own.
    edited = text.replace("- [x] [T https://ex.com/good]", "- [ ] [T https://ex.com/good]").replace(
        "- [ ] [T https://ex.com/weak]", "- [x] [T https://ex.com/weak]"
    )
    edited += "\nhttps://youtube.com/watch?v=abc — great talk\nhttps://arxiv.org/abs/1234\n"
    src.sheet(course).write_text(edited)
    result = src.apply(course)
    assert result["kept"] == 2 and result["dropped"] == 1 and len(result["added"]) == 2
    by_url = {s.url: s for s in src.load(course)}
    assert by_url["https://ex.com/good"].status == "dropped"
    assert by_url["https://ex.com/weak"].status == "kept"
    talk = by_url["https://youtube.com/watch?v=abc"]
    assert (talk.status, talk.type, talk.reason) == ("user", "talk-workshop", "great talk")
    assert by_url["https://arxiv.org/abs/1234"].type == "paper-spec"


def test_apply_rejects_unknown_ids(course):
    src.add(course, [row("https://ex.com/a")])
    src.render(course)
    src.sheet(course).write_text("- [x] whatever <!-- id: nope -->\n")
    with pytest.raises(src.SourcesError, match="unknown ids: nope"):
        src.apply(course)


def test_rows_from_text():
    assert len(src.rows_from_text('[{"a": 1}, {"a": 2}]')) == 2
    assert len(src.rows_from_text('{"a": 1}\n{"a": 2}\n')) == 2
    assert src.rows_from_text('{"a": 1}') == [{"a": 1}]


# --- conversions --------------------------------------------------------------------------


def test_html_to_markdown_keeps_structure():
    html = """<html><head><title>Graph API</title></head><body><nav>menu</nav><article>
    <h1>Graph API</h1><p>A <b>StateGraph</b> has <a href="/nodes">nodes</a>.</p>
    <pre><code>builder.add_node("a", a)</code></pre>
    <p>Second paragraph with enough text to count as main content for the extractor.</p>
    </article></body></html>"""
    title, body = fetch.convert(html.encode(), "text/html", "https://docs.x.dev/graph")
    assert title == "Graph API"
    assert "StateGraph" in body and "add_node" in body


def test_markdown_kept_as_is():
    title, body = fetch.convert(
        b"# LangGraph\n\n- [Docs](https://x)\n", "text/plain", "https://x.dev/llms.txt"
    )
    assert title == "LangGraph" and body.startswith("# LangGraph")


def test_arxiv_abs_resolves_to_pdf():
    assert fetch.resolve_special("https://arxiv.org/abs/2210.03629") == (
        "https://arxiv.org/pdf/2210.03629"
    )


def test_vtt_to_text_drops_timings_and_repeats():
    vtt = (
        "WEBVTT\nKind: captions\nLanguage: en\n\n"
        "00:00:00.000 --> 00:00:02.000\nhello <c>world</c>\n\n"
        "00:00:02.000 --> 00:00:04.000\nhello world\nnext line\n"
    )
    assert research.vtt_to_text(vtt) == "hello world next line"


@pytest.mark.parametrize(
    ("url", "slug"),
    [
        ("https://github.com/langchain-ai/langgraph", "langchain-ai/langgraph"),
        ("git@github.com:langchain-ai/langgraph.git", "langchain-ai/langgraph"),
        ("langchain-ai/langgraph", "langchain-ai/langgraph"),
    ],
)
def test_repo_slug(url, slug):
    assert research.repo_slug(url) == slug


def test_repo_slug_rejects_other_hosts():
    with pytest.raises(research.ResearchError):
        research.repo_slug("https://gitlab.com/a/b")


def test_overview_and_decide(course):
    src.add(
        course,
        [
            row("https://ex.com/good", score=0.8),
            row("https://ex.com/weak", score=0.3),
            row("https://docs.x.dev", "official-docs", score=0.95),
        ],
    )
    groups = src.overview(course)
    assert [g["type"] for g in groups] == ["official-docs", "article"]
    article = {s["url"]: s["default_keep"] for s in groups[1]["sources"]}
    assert article == {"https://ex.com/good": True, "https://ex.com/weak": False}

    weak = next(s.id for s in src.load(course) if s.url.endswith("weak"))
    good = next(s.id for s in src.load(course) if s.url.endswith("good"))
    assert src.decide(course, keep=[weak], drop=[good], default=True) == {"kept": 2, "dropped": 1}
    statuses = {s.url: s.status for s in src.load(course)}
    assert (
        statuses["https://ex.com/weak"] == "kept" and statuses["https://ex.com/good"] == "dropped"
    )
    with pytest.raises(src.SourcesError, match="unknown source ids: nope"):
        src.decide(course, keep=["nope"], drop=[])
