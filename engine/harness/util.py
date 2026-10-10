"""Shared low-level helpers for the harness pipeline (prompt templates, path names)."""

from __future__ import annotations

import re

# Closing fence must start a line, so a horizontal rule inside the body survives.
_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n.*?\r?\n---[ \t]*\r?\n?", re.DOTALL)
_UNSAFE_IN_PATH_RE = re.compile(r"[^\w.+-]+", re.UNICODE)


def strip_frontmatter(text: str) -> str:
    """Remove a leading YAML frontmatter block from a prompt template."""
    return _FRONTMATTER_RE.sub("", text, count=1).strip()


def render_template(template: str, values: dict[str, str]) -> str:
    """Substitute ``{name}`` placeholders in a single pass.

    Single pass matters: skill bodies, model outputs and rubric JSON routinely
    contain placeholder-looking text, which chained ``str.replace`` would expand
    a second time.
    """
    if not values:
        return template
    pattern = re.compile(r"\{(" + "|".join(re.escape(key) for key in values) + r")\}")
    return pattern.sub(lambda match: values[match.group(1)], template)


def safe_path_component(name: str, fallback: str = "skill") -> str:
    """Reduce an arbitrary label (e.g. a SKILL.md name) to one traversal-free path part."""
    cleaned = _UNSAFE_IN_PATH_RE.sub("-", name).strip("-.")
    return cleaned or fallback
