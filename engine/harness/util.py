"""Shared low-level helpers for the harness pipeline (prompt templates, path names)."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Closing fence must start a line, so a horizontal rule inside the body survives.
_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n.*?\r?\n---[ \t]*\r?\n?", re.DOTALL)
_UNSAFE_IN_PATH_RE = re.compile(r"[^\w.+-]+", re.UNICODE)
# A placeholder is a brace holding NOTHING but an identifier. The prompt templates
# also carry JSON examples, whose braces contain quotes and colons, so they never
# match this shape.
_BARE_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def strip_frontmatter(text: str) -> str:
    """Remove a leading YAML frontmatter block from a prompt template."""
    return _FRONTMATTER_RE.sub("", text, count=1).strip()


def template_placeholders(template: str) -> set[str]:
    """Names of the ``{identifier}`` slots a prompt template asks for."""
    return set(_BARE_PLACEHOLDER_RE.findall(template))


def render_template(template: str, values: dict[str, str]) -> str:
    """Substitute ``{name}`` placeholders in a single pass.

    Single pass matters: skill bodies, model outputs and rubric JSON routinely
    contain placeholder-looking text, which chained ``str.replace`` would expand
    a second time.
    """
    if not values:
        return template
    unbound = sorted(template_placeholders(template) - set(values))
    if unbound:
        # A renamed template slot used to ship silently: the prompt went to the
        # model with ``{judge_output}`` still in it.
        logger.warning(
            "prompt template asks for placeholders that were not provided: %s", ", ".join(unbound)
        )
    pattern = re.compile(r"\{(" + "|".join(re.escape(key) for key in values) + r")\}")
    return pattern.sub(lambda match: values[match.group(1)], template)


def safe_path_component(name: str, fallback: str = "skill") -> str:
    """Reduce an arbitrary label (e.g. a SKILL.md name) to one traversal-free path part."""
    cleaned = _UNSAFE_IN_PATH_RE.sub("-", name).strip("-.")
    return cleaned or fallback
