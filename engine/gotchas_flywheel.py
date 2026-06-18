"""GotchasFlywheel module — accumulates experience from eval failures (Issue #42)."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class GotchasFlywheel:
    """Accumulates experience from eval failures.

    After each eval run, extracts patterns from failures and appends
    to a gotchas.md file for future reference. This creates a flywheel
    effect where every failure makes the skill more robust.
    """

    GOTCHAS_FILENAME = "gotchas.md"

    def __init__(self, gotchas_dir: str | Path | None = None):
        self.gotchas_dir = Path(gotchas_dir) if gotchas_dir else Path.cwd() / "references"

    @property
    def gotchas_path(self) -> Path:
        return self.gotchas_dir / self.GOTCHAS_FILENAME

    def extract_from_failure(self, eval_result: dict[str, Any]) -> str | None:
        """Extract gotcha text from a failed eval result.

        Returns a formatted gotcha string, or None if nothing worth capturing.

        Captures:
        - Evals where final_passed is False
        - Evals with assertion failures
        - Evals with ambiguity (low confidence)
        """
        if eval_result.get("final_passed", True):
            return None

        eval_name = eval_result.get("eval_name", "unknown")
        eval_id = eval_result.get("eval_id", "unknown")
        category = eval_result.get("category", "unknown")
        is_negative = eval_result.get("negative_case", False)
        pass_rate = eval_result.get("pass_rate", 0.0)

        # Collect assertion failure details
        assertion_failures = []
        for ar in eval_result.get("assertion_results", []):
            if not ar.get("passed", True):
                assertion_failures.append(
                    f"  - Assertion failed: type={ar.get('assertion_type', 'unknown')}, "
                    f"expected={ar.get('expected', '')}, description={ar.get('description', '')}"
                )

        lines: list[str] = []
        case_type = "should_NOT_trigger" if is_negative else "should_trigger"
        lines.append(
            f"- **Evaluation**: {eval_name} (id={eval_id}, category={category}, type={case_type})"
        )
        lines.append(f"  - **Pass rate**: {pass_rate:.2%}")

        if assertion_failures:
            lines.append("  - **Failure details**:")
            lines.extend(assertion_failures)

        if eval_result.get("judge_result"):
            judge = eval_result["judge_result"]
            if isinstance(judge, dict) and not judge.get("passed", True):
                reason = judge.get("reason", judge.get("explanation", "no reason given"))
                lines.append(f"  - **Judge verdict**: {reason}")

        lines.append("")
        return "\n".join(lines)

    def append(self, gotcha: str) -> None:
        """Append gotcha text to gotchas.md.

        Creates the file and directory if they don't exist.
        """
        self.gotchas_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        entry = (
            f"## Gotcha: {timestamp}\n\n"
            f"{gotcha}\n"
        )

        if self.gotchas_path.exists():
            with open(self.gotchas_path, "a", encoding="utf-8") as f:
                f.write(entry)
        else:
            header = "# Gotchas Flywheel\n\n"
            header += "Accumulated lessons from evaluation failures.\n"
            header += "Each entry captures a scenario where the "
            header += "skill did not behave as expected.\n\n"
            with open(self.gotchas_path, "w", encoding="utf-8") as f:
                f.write(header + entry)

        logger.info("Appended gotcha to %s", self.gotchas_path)

    def process_failures(self, graded_results: list[dict[str, Any]]) -> int:
        """Extract gotchas from all failed evals and append them.

        Args:
            graded_results: List of graded result dicts.

        Returns:
            Number of gotchas appended.
        """
        count = 0
        for result in graded_results:
            gotcha = self.extract_from_failure(result)
            if gotcha:
                self.append(gotcha)
                count += 1
        if count > 0:
            logger.info("Processed %d gotcha(s) from eval failures", count)
        return count

    def load(self) -> list[str]:
        """Load all accumulated gotchas from gotchas.md.

        Returns:
            List of individual gotcha entry strings (without '## Gotcha:' prefix).
        """
        if not self.gotchas_path.exists():
            return []

        text = self.gotchas_path.read_text(encoding="utf-8")
        parts = text.split("## Gotcha:")
        # First part is the header, skip it
        return [p.strip() for p in parts[1:]] if len(parts) > 1 else []
