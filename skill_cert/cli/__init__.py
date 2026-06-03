"""skill-cert CLI package — mode-specific entry points.

Engine symbols are imported FIRST so sub-modules can import from ..
(namely `.. import parse_skill_md`) and test patches via
`skill_cert.cli.parse_skill_md` continue to work.
"""

# ---------------------------------------------------------------------------
# 1. Engine imports — populate module namespace FIRST so sub-module imports
#    (from .. import X) resolve correctly and test patches intercept.
# ---------------------------------------------------------------------------
from engine.analyzer import parse_skill_md  # noqa: E402
from engine.config import SkillCertConfig  # noqa: E402
from engine.dialogue_evaluator import DialogueEvaluator  # noqa: E402
from engine.dialogue_runner import DialogueRunner  # noqa: E402
from engine.drift import DriftDetector  # noqa: E402
from engine.grader import Grader  # noqa: E402
from engine.maintainability import MaintainabilityScorer  # noqa: E402
from engine.metrics import MetricsCalculator  # noqa: E402
from engine.multi_skill import MultiSkillAnalyzer  # noqa: E402
from engine.reliability import ReliabilityTracker  # noqa: E402
from engine.replay import HistoryReplay  # noqa: E402
from engine.reporter import Reporter  # noqa: E402
from engine.runner import EvalRunner  # noqa: E402
from engine.simulator import UserSimulator  # noqa: E402
from engine.stability import StabilityRunner, calculate_l4_stability  # noqa: E402
from engine.stress_test import StressTester, format_scalability_report  # noqa: E402
from engine.testgen import EvalGenerator  # noqa: E402

from .dialogue import run_dialogue_mode  # noqa: E402
from .evals import (  # noqa: E402
    _run_all_evals,
    _run_eval_for_model,
    _run_single_phase,
)
from .helpers import (  # noqa: E402
    EXIT_ERROR,
    EXIT_FAIL_WITH_CAVEATS,
    EXIT_PASS,
    _create_adapter,
    _print_metric,
    _print_phase,
)
from .main import main  # noqa: E402
from .multi_skill import run_multi_skill_mode  # noqa: E402
from .replay import run_replay_mode  # noqa: E402

# ---------------------------------------------------------------------------
# 2. Sub-module imports (these use from engine.xxx too, but also from ..)
# ---------------------------------------------------------------------------
from .setup import run_setup  # noqa: E402
from .single import _setup_single_mode, run_single_mode  # noqa: E402
from .stress import run_stress_mode  # noqa: E402

__all__ = [
    "run_single_mode",
    "run_dialogue_mode",
    "run_replay_mode",
    "run_stress_mode",
    "run_multi_skill_mode",
    "run_setup",
    "EXIT_PASS",
    "EXIT_ERROR",
    "EXIT_FAIL_WITH_CAVEATS",
    "_create_adapter",
    "_print_phase",
    "_print_metric",
    "_run_eval_for_model",
    "_run_all_evals",
    "_run_single_phase",
    "_setup_single_mode",
    "main",
    "parse_skill_md",
    "EvalRunner",
    "Grader",
    "MetricsCalculator",
    "Reporter",
    "DriftDetector",
    "ReliabilityTracker",
    "EvalGenerator",
    "StabilityRunner",
    "calculate_l4_stability",
    "MaintainabilityScorer",
    "StressTester",
    "format_scalability_report",
    "SkillCertConfig",
    "UserSimulator",
    "HistoryReplay",
    "DialogueEvaluator",
    "DialogueRunner",
    "MultiSkillAnalyzer",
]
