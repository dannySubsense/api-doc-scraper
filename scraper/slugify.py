"""
Collision-safe filename derivation for scraper output documents.

identifier_to_slug: converts a platform-native document identifier to a safe
    relative output path (5-step algorithm, per ARCHITECTURE §Filename derivation).

resolve_collisions: given a list of (identifier, candidate_slug) pairs in discovery
    order, returns {identifier: final_slug} with 8-hex SHA-256 suffixes applied where
    needed (ARCHITECTURE §Step 4).
"""

from __future__ import annotations

import hashlib
import re

# Windows reserved filenames (case-insensitive, without extension)
_WINDOWS_RESERVED = frozenset(
    ["con", "prn", "aux", "nul"]
    + [f"com{i}" for i in range(10)]
    + [f"lpt{i}" for i in range(10)]
)

# Maximum byte length for a single sanitized segment (Step 5: 80 bytes)
_SEGMENT_MAX_BYTES = 80
_SEGMENT_HASH_TRIM = 72  # trim to this before appending _<7hex>

# Maximum byte length for the full relative path (Step 5)
_PATH_MAX_BYTES = 200


def _sanitize_segment(segment: str) -> str:
    """
    Apply Steps 2.1–2.6 to a single path segment.
    Returns the sanitized segment (without .md extension).
    """
    original = segment

    # Step 2.1 — Lowercase
    s = segment.lower()

    # Step 2.2 — Strip leading dots
    s = s.lstrip(".")

    # Step 2.3 — Replace illegal characters (not in [a-z0-9._-]) with _
    s = re.sub(r"[^a-z0-9._\-]", "_", s)

    # Step 2.4 — Collapse consecutive underscores
    s = re.sub(r"_+", "_", s)

    # Step 2.5 — Length cap per segment (80 bytes UTF-8)
    if len(s.encode("utf-8")) > _SEGMENT_MAX_BYTES:
        # Truncate original segment to 72 bytes, then append _<7hex>
        orig_hash = hashlib.sha256(original.encode("utf-8")).hexdigest()[:7]
        # Truncate the sanitized string to _SEGMENT_HASH_TRIM bytes
        encoded = s.encode("utf-8")[:_SEGMENT_HASH_TRIM]
        # Decode safely, ignoring incomplete multi-byte sequences
        trimmed = encoded.decode("utf-8", errors="ignore")
        s = f"{trimmed}_{orig_hash}"

    # Step 2.6 — Reserved names (Windows safety)
    if s.lower() in _WINDOWS_RESERVED:
        s = f"{s}_x"

    return s


def _split_identifier(identifier: str, platform: str) -> list[str]:
    """
    Step 1: Split identifier into segments based on platform.

    - docusaurus: URL path, split on "/"
    - github_org: "repo:path" — split on ":" first, then path on "/"
    - readme_io: single segment
    """
    if platform == "docusaurus":
        # Strip scheme+host, query+fragment, then split on /
        path = identifier
        # Strip scheme://host if present
        if "://" in path:
            path = path.split("://", 1)[1]
            if "/" in path:
                path = path[path.index("/"):]
            else:
                path = "/"
        # Strip query and fragment
        path = path.split("?")[0].split("#")[0]
        # Split and filter empty segments
        segments = [s for s in path.split("/") if s]
        return segments if segments else [identifier]

    elif platform == "github_org":
        # Format: "repo:path/to/file.md"
        if ":" in identifier:
            repo, rest = identifier.split(":", 1)
            path_segments = [s for s in rest.split("/") if s]
            return [repo] + path_segments
        else:
            return [identifier]

    else:
        # readme_io: single segment
        return [identifier]


def identifier_to_slug(identifier: str, platform: str) -> str:
    """
    Derive a sanitized relative output path from a document identifier.

    platform: "readme_io" | "docusaurus" | "github_org"
    Returns a relative path string (no leading slash) ending in ".md".
    Does NOT check for collisions — collision detection is the runner's concern.
    """
    # Step 1 — Split into segments
    segments = _split_identifier(identifier, platform)

    if not segments:
        segments = [identifier]

    # Step 2 — Sanitize each segment independently
    sanitized = [_sanitize_segment(seg) for seg in segments]

    # Remove empty segments that result from sanitization (e.g. segment was only dots)
    sanitized = [s for s in sanitized if s] or ["_"]

    # Step 3 — Append .md to the final segment
    last = sanitized[-1]
    # Replace .mdx or .md extension, or append .md
    if last.endswith(".mdx"):
        last = last[:-4] + ".md"
    elif last.endswith(".md"):
        pass  # already correct
    else:
        last = last + ".md"
    sanitized[-1] = last

    # Build the full relative path
    slug = "/".join(sanitized)

    # Step 5 — Total path-length guard (200 bytes)
    slug_bytes = slug.encode("utf-8")
    if len(slug_bytes) > _PATH_MAX_BYTES:
        # Truncate the last segment's stem to fit, then apply hash suffix.
        # Hash is derived from the full original identifier for determinism.
        orig_hash = hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:7]
        hash_suffix = f"_{orig_hash}.md"
        hash_suffix_bytes = len(hash_suffix.encode("utf-8"))  # always 11

        # Calculate how many bytes are available for prefix+sep+stem
        # (total budget minus the hash suffix that must always be appended)
        budget_for_rest = _PATH_MAX_BYTES - hash_suffix_bytes

        prefix_parts = sanitized[:-1]
        last_stem = sanitized[-1]
        if last_stem.endswith(".md"):
            last_stem = last_stem[:-3]

        if prefix_parts:
            sep = "/"
            sep_bytes = 1
            prefix = "/".join(prefix_parts)
            prefix_encoded = prefix.encode("utf-8")
            prefix_byte_len = len(prefix_encoded)
            # Bytes available for the last stem after prefix + separator
            available_for_stem = budget_for_rest - prefix_byte_len - sep_bytes
            if available_for_stem >= 0:
                # Normal case: truncate stem to fit
                stem_encoded = last_stem.encode("utf-8")[:available_for_stem]
                stem_trimmed = stem_encoded.decode("utf-8", errors="ignore")
                new_last = f"{stem_trimmed}{hash_suffix}"
                sanitized[-1] = new_last
            else:
                # Degenerate case: prefix alone exceeds budget.
                # Truncate the prefix itself to leave room for the hash suffix.
                # Drop trailing bytes from prefix until it fits, then use no stem.
                max_prefix_bytes = budget_for_rest - sep_bytes
                if max_prefix_bytes < 0:
                    max_prefix_bytes = 0
                trimmed_prefix = prefix_encoded[:max_prefix_bytes].decode(
                    "utf-8", errors="ignore"
                )
                # Avoid a trailing slash (could appear if truncation landed mid-separator)
                trimmed_prefix = trimmed_prefix.rstrip("/")
                if trimmed_prefix:
                    slug = f"{trimmed_prefix}{hash_suffix}"
                else:
                    slug = hash_suffix.lstrip("_") + ".md" if hash_suffix.startswith("_") else hash_suffix
                return slug
        else:
            # Single-segment path: stem only (no prefix)
            available_for_stem = budget_for_rest
            stem_encoded = last_stem.encode("utf-8")[:available_for_stem]
            stem_trimmed = stem_encoded.decode("utf-8", errors="ignore")
            new_last = f"{stem_trimmed}{hash_suffix}"
            sanitized[-1] = new_last

        slug = "/".join(sanitized)

    return slug


def resolve_collisions(slugs: list[tuple[str, str]]) -> dict[str, str]:
    """
    Given [(identifier, candidate_slug), ...] in discovery order,
    return {identifier: final_slug} with 8-hex SHA-256 suffixes applied where needed.

    The first occurrence of a given candidate_slug retains it unchanged.
    Subsequent collisions get their slug stem replaced with:
        {stem}_{sha256(identifier)[:8]}.md
    """
    seen: dict[str, str] = {}       # candidate_slug -> identifier that claimed it
    result: dict[str, str] = {}

    for identifier, candidate_slug in slugs:
        if candidate_slug not in seen:
            # First occurrence — no collision
            seen[candidate_slug] = identifier
            result[identifier] = candidate_slug
        else:
            # Collision — apply 8-hex suffix based on the full original identifier
            hash8 = hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:8]
            # Split slug into stem + .md
            if candidate_slug.endswith(".md"):
                stem = candidate_slug[:-3]
            else:
                stem = candidate_slug
            # Handle nested paths: only modify the filename part
            parts = stem.rsplit("/", 1)
            if len(parts) == 2:
                dir_part, file_stem = parts
                new_slug = f"{dir_part}/{file_stem}_{hash8}.md"
            else:
                new_slug = f"{stem}_{hash8}.md"
            result[identifier] = new_slug

    return result
