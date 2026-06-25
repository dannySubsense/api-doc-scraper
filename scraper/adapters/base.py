"""
Adapter contract: PlatformAdapter ABC + supporting dataclasses.

Item: one unit of work from discovery.
RunContext: shared context for a single run (config, page, http_get, token).
PlatformAdapter: ABC with abstract discover() and render() methods.
Document: re-exported from emit for adapter convenience.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable

# Re-export Document so adapter modules can import it from here
from scraper.emit import Document


@dataclass
class Item:
    """One unit of work discovered from a target."""
    label: str          # human title / sidebar label
    identifier: str     # slug (readme_io) | URL (docusaurus) | "repo:path" (github_org)
    extra: dict = field(default_factory=dict)
    # readme_io: {}
    # docusaurus: {}
    # github_org: {"repo": str, "default_branch": str, "commit_sha": str | None}


@dataclass
class RunContext:
    config: "TargetConfig"
    page: object        # playwright.sync_api.Page | None; None if not requires_browser
    http_get: Callable[[str], str]   # urllib GET with User-Agent + timeout; raises on non-2xx
    token: str | None   # gh auth token or GITHUB_TOKEN; None for non-github adapters


class PlatformAdapter(ABC):
    name: str
    requires_browser: bool = False

    @abstractmethod
    def discover(self, ctx: RunContext) -> list[Item]:
        """Return all items for the target. May use fallback list if needed."""
        ...

    @abstractmethod
    def render(self, ctx: RunContext, item: Item) -> Document:
        """Fetch + extract + return Document. Raises on unrecoverable error."""
        ...
