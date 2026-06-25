"""
ADAPTERS registry: maps platform name strings to PlatformAdapter subclasses.

Slice 2: readme_io registered.
Docusaurus and github_org adapters registered here as stubs; their full
implementations land in Slices 3 and 4. The registry is validated by
load_target (scraper/config.py) — any listed platform name must have
an entry here, or the CLI will exit 1 with an unknown-platform error.
"""

from scraper.adapters.base import PlatformAdapter  # noqa: F401 — re-export for convenience
from scraper.adapters.readme_io import ReadMeIoAdapter
from scraper.adapters.docusaurus import DocusaurusAdapter
from scraper.adapters.github_org import GitHubOrgAdapter

ADAPTERS: dict[str, type[PlatformAdapter]] = {
    "readme_io": ReadMeIoAdapter,
    "docusaurus": DocusaurusAdapter,
    "github_org": GitHubOrgAdapter,
}
