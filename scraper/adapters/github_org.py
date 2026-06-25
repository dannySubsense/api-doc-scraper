"""
GitHub Org platform adapter.

GitHubOrgAdapter(PlatformAdapter):
  requires_browser = False  — API-based; no browser needed.

discover(ctx):
  Paginates GET /orgs/{org}/repos?per_page=100; skips archived repos unless
  options.include_archived is True. For each repo reads default_branch from the
  API response (FR-11; never hardcodes main). Fetches Git Trees API to enumerate
  documentation paths (FR-12). Fetches head commit SHA for git_ref. Returns
  list[Item] with identifier="repo:path" and
  extra={"repo", "default_branch", "commit_sha"}.

render(ctx, item):
  Fetches raw markdown via raw.githubusercontent.com. Prepends front-matter
  (FR-16a: repo, git_ref="{branch}@{sha}", breadcrumb). Adds # Title heading if
  none present. Returns Document. Self-sufficient on the --slug path: fetches
  default_branch and commit_sha on demand when extra lacks them (G-1).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Optional

from scraper.adapters.base import Item, PlatformAdapter, RunContext
from scraper.emit import Document

_GITHUB_API = "https://api.github.com"
_RAW_BASE = "https://raw.githubusercontent.com"

_USER_AGENT = (
    "Mozilla/5.0 (compatible; api-doc-scraper/0.1; "
    "+https://github.com/islandef/api-doc-scraper-multi-platform)"
)
_HTTP_TIMEOUT = 30


def _api_get(url: str, token: Optional[str]) -> dict | list:
    """Perform a GitHub API GET and return parsed JSON. Raises on non-2xx."""
    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _raw_get(url: str) -> str:
    """Fetch a raw URL and return as text. Raises on non-2xx."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
        return resp.read().decode("utf-8")


def _is_doc_path(path: str) -> bool:
    """
    FR-12 path filter: accept documentation markdown paths.

    Rules:
      1. README* at any depth (case-sensitive match of the basename prefix).
      2. *.md or *.mdx anywhere under docs/ or documentation/ (case-sensitive directory
         prefix match).
      3. Top-level *.md or *.mdx — depth == 1 (no "/" in path).

    Returns True if the path matches any rule.
    """
    basename = path.rsplit("/", 1)[-1]
    depth = path.count("/")

    # Rule 1: README* at any depth
    if basename.startswith("README"):
        return True

    lower_path = path.lower()

    # Rule 2: *.md or *.mdx under docs/ or documentation/
    if lower_path.endswith((".md", ".mdx")):
        if lower_path.startswith("docs/") or lower_path.startswith("documentation/"):
            return True
        # Check for docs/ or documentation/ as a subdirectory
        if "/docs/" in lower_path or "/documentation/" in lower_path:
            return True

    # Rule 3: top-level *.md or *.mdx (depth == 0, i.e. no "/" in path)
    if depth == 0 and lower_path.endswith((".md", ".mdx")):
        return True

    return False


def _fetch_default_branch(org: str, repo: str, token: Optional[str]) -> str:
    """Fetch default_branch for a repo via GET /repos/{owner}/{repo}."""
    url = f"{_GITHUB_API}/repos/{org}/{repo}"
    data = _api_get(url, token)
    return data["default_branch"]


def _fetch_commit_sha(
    org: str, repo: str, branch: str, token: Optional[str]
) -> Optional[str]:
    """Fetch head commit SHA for a branch. Returns None on failure (NFR-4)."""
    url = f"{_GITHUB_API}/repos/{org}/{repo}/commits/{branch}"
    try:
        data = _api_get(url, token)
        if isinstance(data, list):
            # Should be a single commit object, but defend against list response
            data = data[0] if data else {}
        return data.get("sha")
    except Exception as exc:
        print(
            f"  NFR-4: could not fetch commit SHA for {repo}@{branch}: {exc}",
            file=sys.stderr,
        )
        return None


def _github_breadcrumb(repo: str, path: str) -> str:
    """
    Build breadcrumb for a github_org document.

    Format: "{repo} / {path segments, last segment extension stripped}"
    Example: engine + docs/README.md -> "engine / docs / README"
    """
    segments = [s for s in path.split("/") if s]
    if segments:
        # Strip extension from last segment
        last = segments[-1]
        if "." in last:
            last = last.rsplit(".", 1)[0]
        segments[-1] = last
    return " / ".join([repo] + segments) if segments else repo


def _ensure_heading(markdown: str, title: str) -> str:
    """
    Prepend # Title heading if the markdown body has no leading level-1 heading.

    A leading level-1 heading is a line matching ``^# `` (single hash + space)
    appearing before any non-blank content.  Level-2+ headings (``##``, ``###``,
    …) and plain prose both cause the H1 to be prepended so that every document
    carries a top-level title for the embedding corpus.
    """
    stripped = markdown.lstrip()
    if re.match(r"^# ", stripped):
        return markdown
    return f"# {title}\n\n{markdown}"


class GitHubOrgAdapter(PlatformAdapter):
    name = "github_org"
    requires_browser = False

    def discover(self, ctx: RunContext) -> list[Item]:
        """
        Enumerate org repos and documentation paths.

        Paginates /orgs/{org}/repos?per_page=100. For each repo fetches the Git
        Trees API and filters paths per FR-12. Fetches head commit SHA per repo.
        Returns list[Item] with identifier="repo:path".
        """
        org = ctx.config.options.get("org", "")
        if not org:
            print(
                "Error: github_org adapter requires options.org",
                file=sys.stderr,
            )
            sys.exit(1)

        include_archived = ctx.config.options.get("include_archived", False)

        # Paginate repos
        repos = []
        page = 1
        while True:
            url = f"{_GITHUB_API}/orgs/{org}/repos?per_page=100&page={page}"
            try:
                batch = _api_get(url, ctx.token)
            except Exception as exc:
                print(f"  NFR-4: failed to fetch repos page {page}: {exc}", file=sys.stderr)
                break
            if not batch:
                break
            for repo_data in batch:
                if repo_data.get("archived", False) and not include_archived:
                    continue
                repos.append(repo_data)
            if len(batch) < 100:
                break
            page += 1

        print(f"  Repos to scan: {len(repos)}", file=sys.stderr)

        items: list[Item] = []
        for repo_data in repos:
            repo_name = repo_data["name"]
            default_branch = repo_data.get("default_branch") or "main"

            # Fetch Git Tree (recursive)
            tree_url = (
                f"{_GITHUB_API}/repos/{org}/{repo_name}"
                f"/git/trees/{default_branch}?recursive=1"
            )
            try:
                tree_data = _api_get(tree_url, ctx.token)
            except Exception as exc:
                print(
                    f"  NFR-4: skipping repo {repo_name} — tree fetch failed: {exc}",
                    file=sys.stderr,
                )
                continue

            doc_paths = [
                entry["path"]
                for entry in tree_data.get("tree", [])
                if entry.get("type") == "blob" and _is_doc_path(entry["path"])
            ]

            if not doc_paths:
                continue

            # Fetch head commit SHA for this repo
            commit_sha = _fetch_commit_sha(org, repo_name, default_branch, ctx.token)

            for path in doc_paths:
                identifier = f"{repo_name}:{path}"
                label = f"{repo_name}/{path}"
                items.append(
                    Item(
                        label=label,
                        identifier=identifier,
                        extra={
                            "repo": repo_name,
                            "default_branch": default_branch,
                            "commit_sha": commit_sha,
                        },
                    )
                )

        return items

    def render(self, ctx: RunContext, item: Item) -> Document:
        """
        Fetch raw markdown for a github_org item and return a Document.

        Self-sufficient: if extra lacks default_branch/commit_sha (--slug path),
        fetches them on demand before fetching raw content (G-1).

        Prepends front-matter (FR-16a). Adds # Title heading if none present.
        git_ref is "{branch}@{sha}" if commit_sha is not None, else raises
        ValueError (caller records as NFR-4 failure) — per emit.py write_document
        which requires git_ref non-null for github_org (Frank condition #2).
        """
        org = ctx.config.options.get("org", "")

        # Parse repo and path from identifier ("repo:path")
        identifier = item.identifier
        if ":" in identifier:
            repo_name, file_path = identifier.split(":", 1)
        else:
            # Fallback: treat whole identifier as repo, no path
            repo_name = identifier
            file_path = "README.md"

        # G-1: fetch default_branch and commit_sha on demand if not in extra
        default_branch = item.extra.get("default_branch")
        commit_sha = item.extra.get("commit_sha", "MISSING")  # sentinel

        if default_branch is None:
            # --slug entry path: fetch repo metadata on demand
            try:
                default_branch = _fetch_default_branch(org, repo_name, ctx.token)
            except Exception as exc:
                raise ValueError(
                    f"render: cannot fetch default_branch for {repo_name}: {exc}"
                ) from exc
            # Also fetch commit SHA since we're on the --slug path
            commit_sha = _fetch_commit_sha(org, repo_name, default_branch, ctx.token)
        elif commit_sha == "MISSING":
            # extra had default_branch but no commit_sha key (shouldn't happen normally)
            commit_sha = item.extra.get("commit_sha")

        # Build git_ref
        if commit_sha is not None:
            git_ref = f"{default_branch}@{commit_sha}"
        else:
            # NFR-4: commit fetch failed earlier; raise so runner records failure
            raise ValueError(
                f"render: commit_sha is None for {repo_name}:{file_path} — "
                f"recording as NFR-4 failure (git_ref would be null)"
            )

        # Fetch raw markdown
        raw_url = f"{_RAW_BASE}/{org}/{repo_name}/{default_branch}/{file_path}"
        try:
            raw_markdown = _raw_get(raw_url)
        except Exception as exc:
            raise ValueError(
                f"render: raw fetch failed for {raw_url}: {exc}"
            ) from exc

        # Derive title from filename (strip extension, replace hyphens/underscores)
        basename = file_path.rsplit("/", 1)[-1]
        if "." in basename:
            title_stem = basename.rsplit(".", 1)[0]
        else:
            title_stem = basename
        title = title_stem.replace("-", " ").replace("_", " ")

        # If there's a leading # heading in the markdown, use that as title
        first_line_match = re.match(r"^#\s+(.+)", raw_markdown.lstrip())
        if first_line_match:
            title = first_line_match.group(1).strip()

        # Ensure a heading is present
        body_markdown = _ensure_heading(raw_markdown, title)

        # Metadata
        source_url = (
            f"https://github.com/{org}/{repo_name}/blob/{default_branch}/{file_path}"
        )
        breadcrumb = _github_breadcrumb(repo_name, file_path)
        content_hash = hashlib.sha256(body_markdown.encode("utf-8")).hexdigest()
        fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # slug: carried from runner via item.extra["_slug"]
        slug = item.extra.get("_slug", "")

        metadata = {
            "source_url": source_url,
            "title": title,
            "platform": "github_org",
            "target": ctx.config.name,
            "package": None,
            "repo": repo_name,
            "breadcrumb": breadcrumb,
            "fetched_at": fetched_at,
            "content_hash": content_hash,
            "git_ref": git_ref,
        }

        return Document(
            slug=slug,
            title=title,
            body_markdown=body_markdown,
            metadata=metadata,
        )
