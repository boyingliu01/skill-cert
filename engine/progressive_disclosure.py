"""Progressive disclosure evaluation — TieredCostModel + progressive_disclosure_test.

Implements the three-tier cost model (Index/Load/Runtime) and verifies
that skill directories support on-demand references loading rather than
loading everything into context at once.

References:
    - Anthropic Skill methodology: skill is a folder, not a file
    - Perplexity three-tier cost model: Index < 100t, Load < 5000t
    - Issue #41: progressive disclosure evaluation
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Default Thresholds ─────────────────────────────────────────

INDEX_TOKEN_LIMIT = 100  # Index: name + description, paid every session
LOAD_TOKEN_LIMIT = 5000  # Load: full SKILL.md, paid when skill triggers
RUNTIME_UNLIMITED = True  # Runtime: references/ loaded on-demand, no hard cap


# ── Tiered Cost Model ──────────────────────────────────────────


@dataclass
class TierCost:
    """Token cost for a single tier."""

    tier_name: str  # 'index' | 'load' | 'runtime'
    token_count: int
    file_count: int
    files: list[str] = field(default_factory=list)
    over_budget: bool = False
    budget: int = 0


@dataclass
class TieredCostResult:
    """Complete three-tier cost analysis result."""

    index: TierCost
    load: TierCost
    runtime: TierCost
    total_tokens: int = 0
    all_within_budget: bool = False
    alerts: list[str] = field(default_factory=list)

    @property
    def roe_ratio(self) -> float:
        """Return on engagement: runtime / (index + load).

        A high ratio means most tokens are paid on-demand (good).
        A low ratio means most tokens are paid upfront (bad for complex skills).
        """
        denominator = self.index.token_count + self.load.token_count
        if denominator == 0:
            return float("inf")
        return self.runtime.token_count / denominator


class TieredCostModel:
    """Three-tier token cost analysis for skill directories.

    Analyzes a skill directory and computes token costs for each tier:
    - Index: name + description (always loaded)
    - Load: full SKILL.md content (loaded when skill triggers)
    - Runtime: references/ files (loaded on-demand)

    Usage:
        model = TieredCostModel(skill_dir="/path/to/skill")
        result = model.analyze()
    """

    INDEX_TOKEN_LIMIT = INDEX_TOKEN_LIMIT
    LOAD_TOKEN_LIMIT = LOAD_TOKEN_LIMIT

    def __init__(
        self,
        skill_dir: str | Path,
        index_token_limit: int = INDEX_TOKEN_LIMIT,
        load_token_limit: int = LOAD_TOKEN_LIMIT,
    ):
        self.skill_dir = Path(skill_dir)
        self.index_token_limit = index_token_limit
        self.load_token_limit = load_token_limit

    def _count_tokens(self, text: str) -> int:
        """Approximate token count (4 chars per token)."""
        return len(text) // 4

    def _read_text(self, path: Path) -> str:
        """Safely read a text file, return empty string on error."""
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            logger.warning("Could not read file: %s", path)
            return ""

    def _analyze_index_tier(self) -> TierCost:
        """Analyze index tier: skill name + description from SKILL.md frontmatter."""
        skill_path = self.skill_dir / "SKILL.md"
        if not skill_path.exists():
            return TierCost(
                tier_name="index",
                token_count=0,
                file_count=0,
                over_budget=False,
                budget=self.index_token_limit,
            )

        content = self._read_text(skill_path)
        if not content:
            return TierCost(
                tier_name="index",
                token_count=0,
                file_count=0,
                over_budget=False,
                budget=self.index_token_limit,
            )

        # Extract name and description from frontmatter
        name = "unknown"
        description = ""
        import re

        fm_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
        if fm_match:
            for line in fm_match.group(1).splitlines():
                if line.startswith("name:"):
                    name = line.split(":", 1)[1].strip().strip("\"'")
                elif line.startswith("description:"):
                    description = line.split(":", 1)[1].strip().strip("\"'")

        # Index content = name + description
        index_text = f"{name} {description}"
        token_count = self._count_tokens(index_text)

        return TierCost(
            tier_name="index",
            token_count=token_count,
            file_count=1,
            files=["SKILL.md (name + description)"],
            over_budget=token_count > self.index_token_limit,
            budget=self.index_token_limit,
        )

    def _analyze_load_tier(self) -> TierCost:
        """Analyze load tier: full SKILL.md content."""
        skill_path = self.skill_dir / "SKILL.md"
        if not skill_path.exists():
            return TierCost(
                tier_name="load",
                token_count=0,
                file_count=0,
                over_budget=False,
                budget=self.load_token_limit,
            )

        content = self._read_text(skill_path)
        token_count = self._count_tokens(content)

        return TierCost(
            tier_name="load",
            token_count=token_count,
            file_count=1,
            files=["SKILL.md (full content)"],
            over_budget=token_count > self.load_token_limit,
            budget=self.load_token_limit,
        )

    def _analyze_runtime_tier(self) -> TierCost:
        """Analyze runtime tier: all files in references/ and subdirectories."""
        ref_dir = self.skill_dir / "references"
        if not ref_dir.exists() or not ref_dir.is_dir():
            return TierCost(
                tier_name="runtime",
                token_count=0,
                file_count=0,
                over_budget=False,
                budget=0,
            )

        files: list[str] = []
        total_tokens = 0

        for fpath in sorted(ref_dir.rglob("*")):
            if fpath.is_file() and not fpath.name.startswith("."):
                rel = str(fpath.relative_to(self.skill_dir))
                content = self._read_text(fpath)
                total_tokens += self._count_tokens(content)
                files.append(rel)

        return TierCost(
            tier_name="runtime",
            token_count=total_tokens,
            file_count=len(files),
            files=files,
            over_budget=False,  # Runtime is on-demand, no hard cap
            budget=0,
        )

    def analyze(self) -> TieredCostResult:
        """Run full three-tier analysis on the skill directory.

        Returns:
            TieredCostResult with per-tier costs and budget status.
        """
        index = self._analyze_index_tier()
        load = self._analyze_load_tier()
        runtime = self._analyze_runtime_tier()

        total = index.token_count + load.token_count + runtime.token_count
        all_ok = not index.over_budget and not load.over_budget

        alerts: list[str] = []
        if index.over_budget:
            alerts.append(
                f"Index tier {index.token_count}t exceeds limit "
                f"({self.index_token_limit}t). "
                f"Reduce name/description length."
            )
        if load.over_budget:
            alerts.append(
                f"Load tier {load.token_count}t exceeds limit "
                f"({self.load_token_limit}t). "
                f"Consider splitting SKILL.md or using references/."
            )

        return TieredCostResult(
            index=index,
            load=load,
            runtime=runtime,
            total_tokens=total,
            all_within_budget=all_ok,
            alerts=alerts,
        )


# ── Progressive Disclosure Test ────────────────────────────────


@dataclass
class ProgressiveDisclosureResult:
    """Result of the progressive disclosure test."""

    passed: bool = False
    has_references_dir: bool = False
    references_file_count: int = 0
    references_token_count: int = 0
    runtime_to_index_ratio: float = 0.0
    tiered_cost_result: TieredCostResult | None = None
    issues: list[str] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        """PASS if progressive disclosure is properly implemented."""
        if self.passed:
            return "PASS"
        return "FAIL"


def progressive_disclosure_test(skill_dir: str | Path) -> ProgressiveDisclosureResult:
    """Verify that a skill directory supports progressive disclosure.

    Progressive disclosure means:
    1. SKILL.md loads only Index (name + description) by default (< 100t)
    2. Full SKILL.md loads on trigger (< 5000t)
    3. references/ files are loaded on-demand (not prepended to every prompt)

    Args:
        skill_dir: Path to the skill directory containing SKILL.md.

    Returns:
        ProgressiveDisclosureResult with test verdict and details.
    """
    skill_path = Path(skill_dir)
    issues: list[str] = []

    if not skill_path.exists():
        return ProgressiveDisclosureResult(
            passed=False, issues=[f"Skill directory not found: {skill_dir}"]
        )

    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        return ProgressiveDisclosureResult(
            passed=False, issues=[f"SKILL.md not found in {skill_dir}"]
        )

    # Run tiered cost analysis
    cost_model = TieredCostModel(skill_dir)
    cost_result = cost_model.analyze()

    # Check for references/ directory
    ref_dir = skill_path / "references"
    has_refs = ref_dir.exists() and ref_dir.is_dir()
    ref_files = list(ref_dir.rglob("*")) if has_refs else []
    ref_file_count = len([f for f in ref_files if f.is_file() and not f.name.startswith(".")])

    # Evaluate progressive disclosure
    all_good = True

    if cost_result.index.over_budget:
        issues.append(
            f"Index tier too large: {cost_result.index.token_count}t "
            f"(limit: {INDEX_TOKEN_LIMIT}t). "
            "Name + description should be concise."
        )
        all_good = False

    if cost_result.load.over_budget:
        issues.append(
            f"Load tier too large: {cost_result.load.token_count}t "
            f"(limit: {LOAD_TOKEN_LIMIT}t). "
            "Consider moving detailed instructions to references/."
        )
        all_good = False

    if not has_refs and cost_result.load.token_count > LOAD_TOKEN_LIMIT * 0.5:
        issues.append(
            "No references/ directory found. "
            "Skills over 2500t should use references/ for on-demand loading."
        )
        all_good = False

    if cost_result.runtime.file_count > 0:
        rt_ratio = cost_result.roe_ratio
        if rt_ratio < 1.0 and cost_result.runtime.token_count > 0:
            issues.append(
                f"Runtime tier ({cost_result.runtime.token_count}t) is smaller than "
                f"index+load ({cost_result.index.token_count + cost_result.load.token_count}t). "
                "Consider moving content to references/ for true progressive disclosure."
            )
    else:
        rt_ratio = 0.0

    return ProgressiveDisclosureResult(
        passed=all_good,
        has_references_dir=has_refs,
        references_file_count=ref_file_count,
        references_token_count=cost_result.runtime.token_count,
        runtime_to_index_ratio=round(rt_ratio, 2),
        tiered_cost_result=cost_result,
        issues=issues,
    )
