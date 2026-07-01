"""Tests for evals cache versioning and invalidation logic."""

import json
from pathlib import Path

from engine.constants import TESTGEN_LOGIC_VERSION
from skill_cert.cli.evals import _read_evals_cache, _write_evals_cache


def test_cache_invalidation_on_version_bump(tmp_path: Path) -> None:
    """Given a cache written with an old version, reading it should invalidate and return None."""
    # Arrange: write cache with a version that doesn't match current
    skill_content = "# My Skill\nSome instructions."
    old_cache = {
        "testgen_version": "1.0",
        "skill_content_hash": "old_hash",
        "eval_cases": [{"id": 1, "name": "test"}],
    }
    cache_file = tmp_path / "my-skill-evals-cache.json"
    cache_file.write_text(json.dumps(old_cache), encoding="utf-8")

    # Act: read with current version
    result = _read_evals_cache(tmp_path, "my-skill", skill_content)

    # Assert: cache invalidated, file deleted, returns None
    assert result is None
    assert not cache_file.exists()


def test_cache_invalidation_on_skill_content_change(tmp_path: Path) -> None:
    """Given a cache with a different skill content hash, reading should invalidate."""
    # Arrange: write cache with current version but different content hash
    skill_content = "# Updated Skill\nNew instructions here."
    old_cache = {
        "testgen_version": TESTGEN_LOGIC_VERSION,
        "skill_content_hash": "sha256:different_hash_value",
        "eval_cases": [{"id": 1, "name": "test"}],
    }
    cache_file = tmp_path / "my-skill-evals-cache.json"
    cache_file.write_text(json.dumps(old_cache), encoding="utf-8")

    # Act: read with the actual skill content
    result = _read_evals_cache(tmp_path, "my-skill", skill_content)

    # Assert: cache invalidated due to hash mismatch, file deleted
    assert result is None
    assert not cache_file.exists()


def test_cache_no_invalidation_same_version(tmp_path: Path) -> None:
    """Given a valid cache with matching version and hash, reading should return the data."""
    # Arrange: write cache via the write function (ensures correct hash)
    skill_content = "# Stable Skill\nSame instructions."
    evals_data = {"eval_cases": [{"id": 1, "name": "test"}]}
    _write_evals_cache(tmp_path, "my-skill", evals_data, skill_content)

    # Act: read back with same content
    result = _read_evals_cache(tmp_path, "my-skill", skill_content)

    # Assert: cache returned successfully, file still exists
    assert result is not None
    assert result["testgen_version"] == TESTGEN_LOGIC_VERSION
    assert result["eval_cases"] == [{"id": 1, "name": "test"}]
    assert (tmp_path / "my-skill-evals-cache.json").exists()
