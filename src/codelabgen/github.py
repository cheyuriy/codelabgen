"""GitHub access for research: `gh` if logged in, else $GITHUB_TOKEN, else anonymous.

Anonymous access has 60 requests per hour and no code search or GraphQL
(discussions), so research gets thinner but still works.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from functools import cache

import httpx

API = "https://api.github.com"


class GitHubError(Exception):
    pass


class Unavailable(GitHubError):
    """The operation needs authentication that is not configured."""


@dataclass(frozen=True)
class Access:
    mode: str  # "gh" | "token" | "anonymous"
    detail: str


@cache
def access() -> Access:
    if shutil.which("gh"):
        status = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True)
        if status.returncode == 0:
            return Access("gh", "gh CLI, logged in")
    if os.environ.get("GITHUB_TOKEN"):
        return Access("token", "GITHUB_TOKEN")
    return Access("anonymous", "no authentication: 60 requests/hour, no code search or discussions")


def rest(path: str, params: dict | None = None) -> dict | list:
    """GET a REST endpoint and return the decoded JSON."""
    mode = access().mode
    params = {k: v for k, v in (params or {}).items() if v is not None}
    if mode == "gh":
        argv = ["gh", "api", "-X", "GET", path]
        for key, value in params.items():
            argv += ["-f", f"{key}={value}"]
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            raise GitHubError(f"gh api {path}: {(proc.stderr or proc.stdout).strip()[:300]}")
        return json.loads(proc.stdout or "null")
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if mode == "token":
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    response = httpx.get(f"{API}/{path.lstrip('/')}", params=params, headers=headers, timeout=30)
    if response.status_code == 403 and "rate limit" in response.text.lower():
        raise GitHubError(
            "GitHub rate limit reached; log in with `gh auth login` or set GITHUB_TOKEN"
        )
    if response.status_code >= 400:
        raise GitHubError(f"GET {path}: HTTP {response.status_code}: {response.text[:200]}")
    return response.json()


def graphql(query: str, variables: dict) -> dict:
    mode = access().mode
    if mode == "anonymous":
        raise Unavailable("GitHub GraphQL needs authentication (gh auth login or GITHUB_TOKEN)")
    if mode == "gh":
        argv = ["gh", "api", "graphql", "-f", f"query={query}"]
        for key, value in variables.items():
            argv += ["-F" if isinstance(value, int) else "-f", f"{key}={value}"]
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            raise GitHubError(f"gh api graphql: {(proc.stderr or proc.stdout).strip()[:300]}")
        data = json.loads(proc.stdout)
    else:
        response = httpx.post(
            f"{API}/graphql",
            json={"query": query, "variables": variables},
            headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}"},
            timeout=30,
        )
        data = response.json()
    if data.get("errors"):
        raise GitHubError(f"graphql: {data['errors'][0].get('message')}")
    return data["data"]


# --- research operations -----------------------------------------------------------------


def repo_meta(repo: str) -> dict:
    data = rest(f"repos/{repo}")
    return {
        "repo": data["full_name"],
        "description": data.get("description"),
        "stars": data.get("stargazers_count"),
        "forks": data.get("forks_count"),
        "pushed_at": data.get("pushed_at"),
        "archived": data.get("archived"),
        "license": (data.get("license") or {}).get("spdx_id"),
        "topics": data.get("topics", []),
        "default_branch": data.get("default_branch"),
        "homepage": data.get("homepage"),
        "url": data.get("html_url"),
    }


def search_repos(query: str, limit: int = 20, sort: str | None = "stars") -> list[dict]:
    data = rest("search/repositories", {"q": query, "sort": sort, "per_page": min(limit, 100)})
    return [
        {
            "repo": item["full_name"],
            "description": item.get("description"),
            "stars": item.get("stargazers_count"),
            "pushed_at": item.get("pushed_at"),
            "archived": item.get("archived"),
            "topics": item.get("topics", []),
            "url": item.get("html_url"),
        }
        for item in data.get("items", [])[:limit]
    ]


def search_code(query: str, limit: int = 20) -> list[dict]:
    if access().mode == "anonymous":
        raise Unavailable("GitHub code search needs authentication (gh auth login or GITHUB_TOKEN)")
    data = rest("search/code", {"q": query, "per_page": min(limit, 100)})
    return [
        {
            "repo": item["repository"]["full_name"],
            "path": item["path"],
            "url": item.get("html_url"),
        }
        for item in data.get("items", [])[:limit]
    ]


def top_issues(repo: str, query: str = "", limit: int = 20, state: str | None = None) -> list[dict]:
    """Most-reacted issues of a repo, optionally filtered by a search query."""
    parts = [f"repo:{repo}", "is:issue", query]
    if state:
        parts.append(f"is:{state}")
    data = rest(
        "search/issues",
        {
            "q": " ".join(p for p in parts if p),
            "sort": "reactions",
            "order": "desc",
            "per_page": min(limit, 100),
        },
    )
    return [
        {
            "title": item["title"],
            "url": item["html_url"],
            "state": item["state"],
            "reactions": (item.get("reactions") or {}).get("total_count", 0),
            "comments": item.get("comments", 0),
            "labels": [label["name"] for label in item.get("labels", [])],
            "created_at": item.get("created_at"),
            "body": (item.get("body") or "")[:1500],
        }
        for item in data.get("items", [])[:limit]
    ]


DISCUSSIONS_QUERY = """
query($owner: String!, $name: String!, $count: Int!) {
  repository(owner: $owner, name: $name) {
    discussions(first: $count, orderBy: {field: UPDATED_AT, direction: DESC}) {
      nodes {
        title url upvoteCount createdAt
        category { name }
        comments { totalCount }
        answer { body }
        bodyText
      }
    }
  }
}
"""


def top_discussions(repo: str, limit: int = 20) -> list[dict]:
    """Recent discussions (up to 100 scanned), ranked by upvotes and comments."""
    owner, name = repo.split("/", 1)
    data = graphql(DISCUSSIONS_QUERY, {"owner": owner, "name": name, "count": 100})
    nodes = (data.get("repository") or {}).get("discussions", {}).get("nodes", [])
    ranked = sorted(
        nodes, key=lambda n: (n["upvoteCount"], n["comments"]["totalCount"]), reverse=True
    )
    return [
        {
            "title": n["title"],
            "url": n["url"],
            "category": (n.get("category") or {}).get("name"),
            "upvotes": n["upvoteCount"],
            "comments": n["comments"]["totalCount"],
            "answered": bool(n.get("answer")),
            "created_at": n.get("createdAt"),
            "body": (n.get("bodyText") or "")[:1500],
            "answer": ((n.get("answer") or {}).get("body") or "")[:1500],
        }
        for n in ranked[:limit]
    ]


def issues_markdown(repo: str, items: list[dict], kind: str) -> str:
    lines = [f"# Top {kind} of {repo}", ""]
    for item in items:
        score = item.get("reactions", item.get("upvotes", 0))
        lines += [
            f"## {item['title']}",
            "",
            f"{item['url']} · score {score} · comments {item['comments']}"
            + (f" · {item['state']}" if "state" in item else "")
            + (f" · labels: {', '.join(item['labels'])}" if item.get("labels") else "")
            + (" · answered" if item.get("answered") else ""),
            "",
            item["body"].strip(),
            "",
        ]
        if item.get("answer"):
            lines += ["**Accepted answer:**", "", item["answer"].strip(), ""]
    return "\n".join(lines)
