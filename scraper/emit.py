"""
Emit layer: atomic document and manifest writes.

Document dataclass holds the render result.
_atomic_write: write-to-temp-then-os.replace pattern (NFR-4, S3).
write_document: validate FR-16a fields, render YAML front-matter, atomic write.
write_manifest: build manifest dict per ARCHITECTURE schema, atomic write once.
write_all: convenience wrapper.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml


# Non-nullable fields required in every Document.metadata (FR-16a)
_REQUIRED_NON_NULLABLE = frozenset(
    ["source_url", "title", "platform", "target", "fetched_at", "content_hash"]
)

# All keys that must be present (including nullable ones)
_REQUIRED_KEYS = frozenset(
    [
        "source_url",
        "title",
        "platform",
        "target",
        "package",
        "repo",
        "breadcrumb",
        "fetched_at",
        "content_hash",
        "git_ref",
    ]
)


@dataclass
class Document:
    """The render result; maps to exactly one output file."""
    slug: str           # relative output path (see §Filename derivation); no leading slash
    title: str
    body_markdown: str
    metadata: dict      # all fields from FR-16a; null values must be explicitly present


def _atomic_write(path: Path, content: str) -> None:
    """Write content to path atomically. Safe against interrupted runs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, path)  # atomic on POSIX; best-effort on Windows
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def write_document(doc: Document, cfg: "TargetConfig") -> None:
    """
    Validate all non-nullable FR-16a fields, render YAML front-matter, atomic write.

    Raises ValueError if a required non-nullable field is missing or empty.
    For github_org documents, git_ref must also be non-null (FR-16a, Frank condition #2).
    The github_org adapter (Slice 4) must never pass a null git_ref here; if the commits
    endpoint fails, the adapter records the item as a FAILURE per NFR-4 instead.
    Caller (runner/write_all) is responsible for catching and recording failures.
    """
    # Validate required non-nullable fields
    for key in _REQUIRED_NON_NULLABLE:
        val = doc.metadata.get(key)
        if val is None or val == "":
            raise ValueError(f'missing required field "{key}"')

    # FR-16a: for github_org platform, git_ref must be present AND non-null
    if doc.metadata.get("platform") == "github_org":
        if doc.metadata.get("git_ref") is None:
            raise ValueError('missing required field "git_ref"')

    # Render YAML front-matter
    front_matter_yaml = yaml.dump(
        doc.metadata,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=True,
    )
    content = f"---\n{front_matter_yaml}---\n\n{doc.body_markdown}"

    # Determine output path
    project_root = Path(__file__).parent.parent
    output_path = project_root / cfg.output_dir / doc.slug

    _atomic_write(output_path, content)


def write_manifest(
    docs: list[Document],
    failures: list[dict],
    cfg: "TargetConfig",
) -> None:
    """
    Build manifest dict per ARCHITECTURE schema, write once atomically.

    Called once after the render loop completes — never written incrementally.
    """
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    manifest = {
        "target": cfg.name,
        "platform": cfg.platform,
        "generated_at": generated_at,
        "document_count": len(docs),
        "failure_count": len(failures),
        "documents": [
            {
                "slug": doc.slug,
                "title": doc.title,
                "source_url": doc.metadata.get("source_url", ""),
                "content_hash": doc.metadata.get("content_hash", ""),
            }
            for doc in docs
        ],
        "failures": failures,
    }

    project_root = Path(__file__).parent.parent
    manifest_path = project_root / cfg.output_dir / "manifest.json"

    _atomic_write(manifest_path, json.dumps(manifest, indent=2, ensure_ascii=False))


def write_all(
    docs: list[Document],
    failures: list[dict],
    cfg: "TargetConfig",
) -> None:
    """
    Convenience wrapper: write each document atomically, then write manifest once.

    Handles single_file mode (FR-18) when cfg.output_mode == "single_file".
    """
    if cfg.output_mode == "single_file":
        _write_single_file(docs, cfg)
    else:
        for doc in docs:
            write_document(doc, cfg)

    write_manifest(docs, failures, cfg)


def _write_single_file(docs: list[Document], cfg: "TargetConfig") -> None:
    """
    FR-18: concatenate all document bodies into one file (AskEdgar regression parity).
    Output path: output/<target>/<target>.md
    """
    project_root = Path(__file__).parent.parent
    output_path = project_root / cfg.output_dir / f"{cfg.name}.md"

    parts: list[str] = []
    for doc in docs:
        # Build front-matter
        front_matter_yaml = yaml.dump(
            doc.metadata,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=True,
        )
        parts.append(f"---\n{front_matter_yaml}---\n\n{doc.body_markdown}")
        parts.append("\n---\n")

    content = "\n".join(parts)
    _atomic_write(output_path, content)
