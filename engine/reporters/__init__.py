"""Reporters package — report generation for skill-cert engine.

Submodules:
- formatters: String/numeric formatting helpers (num, redact_config)
- builders: Data preparation and section-building functions
- generator: Reporter class for Markdown + JSON report generation
"""

from engine.reporters.generator import Reporter

__all__ = ["Reporter"]
