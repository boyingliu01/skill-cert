"""Backward-compatible facade for the reporters package.

Re-exports Reporter from engine.reporters.generator so that all existing
imports like ``from engine.reporter import Reporter`` continue to work
without modification.
"""

from engine.reporters.generator import Reporter

__all__ = ["Reporter"]
