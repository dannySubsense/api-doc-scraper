"""
Regression tests for output_dir safety validation.

Covers two defence layers:
  1. config.load_target — fast-fail validation rejects unsafe output_dir values
     before any destructive operation runs.
  2. runner — containment check ensures rmtree is not called when resolved path
     escapes cwd (belt-and-suspenders, even if config validation passes).

AC refs: Slice 3 Fix Attempt 2 (safety guard).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scraper.config import TargetConfig


# ---------------------------------------------------------------------------
# Helper — write a temp target yaml and call load_target, then always clean up
# ---------------------------------------------------------------------------

_TARGETS_DIR = Path(__file__).parent.parent / "targets"


def _load_with_output_dir(output_dir_line: str, tmp_name: str = "_safety_test") -> TargetConfig:
    """
    Write a minimal targets/{tmp_name}.yaml with the given output_dir line,
    call load_target, then always delete the temp file.

    Raises SystemExit(1) if config validation rejects the output_dir.
    Skips if the docusaurus adapter is not yet registered (platform check
    happens before output_dir validation, so the test is not meaningful
    without a valid platform).
    """
    import scraper.config as _cfg_mod
    from scraper.adapters import ADAPTERS

    if "docusaurus" not in ADAPTERS:
        pytest.skip("docusaurus adapter not registered — skipping config safety test")

    yaml_path = _TARGETS_DIR / f"{tmp_name}.yaml"
    try:
        yaml_path.write_text(
            f"platform: docusaurus\n{output_dir_line}\n",
            encoding="utf-8",
        )
        return _cfg_mod.load_target(tmp_name)
    finally:
        if yaml_path.exists():
            yaml_path.unlink()


# ---------------------------------------------------------------------------
# Layer 1 — config.py validation (fast-fail at load time)
# ---------------------------------------------------------------------------

class TestConfigOutputDirValidation:
    """load_target must reject unsafe output_dir values with SystemExit(1)."""

    def test_rejects_empty_string(self):
        """An explicit empty string for output_dir must be rejected."""
        with pytest.raises(SystemExit) as exc_info:
            _load_with_output_dir('output_dir: ""', "_safety_empty")
        assert exc_info.value.code == 1

    def test_rejects_dot(self):
        """output_dir: "." must be rejected (would wipe working directory)."""
        with pytest.raises(SystemExit) as exc_info:
            _load_with_output_dir('output_dir: "."', "_safety_dot")
        assert exc_info.value.code == 1

    def test_rejects_absolute_path(self):
        """An absolute path must be rejected."""
        with pytest.raises(SystemExit) as exc_info:
            _load_with_output_dir('output_dir: "/abs/path"', "_safety_abs")
        assert exc_info.value.code == 1

    def test_rejects_dotdot_escape(self):
        """output_dir: "../escape" must be rejected (dotdot component)."""
        with pytest.raises(SystemExit) as exc_info:
            _load_with_output_dir('output_dir: "../escape"', "_safety_dotdot")
        assert exc_info.value.code == 1

    def test_rejects_nested_dotdot_escape(self):
        """output_dir: "a/../../b" must be rejected (dotdot component present)."""
        with pytest.raises(SystemExit) as exc_info:
            _load_with_output_dir('output_dir: "a/../../b"', "_safety_nested_dotdot")
        assert exc_info.value.code == 1

    def test_accepts_valid_relative_path(self):
        """A clean relative path like "output/x" must load without error."""
        cfg = _load_with_output_dir('output_dir: "output/x"', "_safety_valid")
        assert cfg.output_dir == "output/x"

    def test_accepts_default_output_dir(self):
        """When output_dir is absent from YAML the default output/{name} must be used."""
        cfg = _load_with_output_dir("", "_safety_default")
        assert cfg.output_dir == "output/_safety_default"


# ---------------------------------------------------------------------------
# Layer 2 — runner.py containment check (belt-and-suspenders)
# ---------------------------------------------------------------------------

class TestRunnerContainmentGuard:
    """
    The runner must NOT call shutil.rmtree when output_dir resolves outside cwd.

    We construct a TargetConfig directly (bypassing load_target validation) to
    simulate a cfg whose output_dir escaped validation, and verify the runner's
    own guard triggers before rmtree is reached.
    """

    def _make_cfg(self, output_dir: str) -> TargetConfig:
        return TargetConfig(
            name="test",
            platform="docusaurus",
            output_dir=output_dir,
            output_mode="per_doc",
        )

    def test_rmtree_not_called_for_escaping_path(self, tmp_path: Path, monkeypatch):
        """
        If output_dir resolves outside cwd the runner returns exit-code 1
        without calling shutil.rmtree.

        Note: the rmtree guard fires AFTER discovery (discover is intentionally
        read-only per spec), so the fake adapter's discover returns one synthetic
        item to allow the flow to reach the containment check.
        """
        import argparse
        import scraper.runner as _runner

        # cd into a subdirectory so that "../escape" resolves outside it
        fake_cwd = tmp_path / "workdir"
        fake_cwd.mkdir()
        monkeypatch.chdir(fake_cwd)

        cfg = self._make_cfg("../escape")

        rmtree_calls: list = []

        def fake_rmtree(path, *args, **kwargs):
            rmtree_calls.append(path)

        from scraper.adapters.base import Item

        class _FakeAdapter:
            name = "docusaurus"
            requires_browser = False

            def discover(self, ctx):
                # One synthetic item so the flow reaches the rmtree containment guard
                return [Item(label="test-page", identifier="test-page")]

            def render(self, ctx, item):
                raise AssertionError("should not reach render — guard must fire first")

        monkeypatch.setattr(_runner, "load_target", lambda n: cfg)
        monkeypatch.setitem(_runner.ADAPTERS, "docusaurus", lambda: _FakeAdapter())
        # The runner does `import shutil as _shutil` inside the function body,
        # so patch the shutil module directly.
        monkeypatch.setattr(shutil, "rmtree", fake_rmtree)

        args = argparse.Namespace(
            target="test",
            slug=None,
            no_discover=False,
            discover=False,
            limit=None,
        )

        result = _runner.run(args)

        assert result == 1, "runner should return exit-code 1 for escaping output_dir"
        assert rmtree_calls == [], "shutil.rmtree must NOT have been called"
