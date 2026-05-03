# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

skill-cert — 通用 AI Skill 评测引擎。接收任意 SKILL.md，自动解析、生成测试、跨模型执行、L1-L4 打分、漂移检测、输出 PASS/FAIL 报告。

## Commands

```bash
pip install -e .                                    # Install
skill-cert --skill /path/to/SKILL.md --models m1,m2 # Run evaluation
skill-cert --skill SKILL.md --mode dialogue --max-turns 10  # Dialogue mode
skill-cert --skill SKILL.md --mode replay --session session.jsonl  # Replay mode
pytest                                              # Run all tests
pytest tests/test_analyzer.py                       # Single test file
pytest tests/test_analyzer.py::test_parse_skill_md  # Single test
pytest --cov=engine --cov=skill_cert --cov=adapters --cov-report=term-missing  # Coverage
ruff check .                                        # Lint
black . && isort .                                  # Format
python scripts/run_uat.py                           # UAT against real skills
python scripts/verify_uat.py                        # Verify API config
```

## Architecture

3-layer clean architecture defined in `architecture.yaml`:

| Layer | Directory | Role | Can import |
|-------|-----------|------|------------|
| Domain | `engine/` | Core pipeline (13 modules) | adapters, prompts, schemas, templates |
| Infrastructure | `adapters/` | LLM provider adapters | nothing from engine or skill_cert |
| Presentation | `skill_cert/` | CLI entry point | engine, adapters |

Support: `prompts/` (LLM prompt templates), `schemas/` (JSON schemas), `templates/` (fallback evals)

## Pipeline (6 Phases)

```
Phase 0: parse_skill_md() → SkillSpec (regex + AST, LLM fallback)
Phase 1: EvalGenerator → Review → Gap-fill loop until coverage ≥ 90%
Phase 2: Runner executes with-skill vs without-skill (concurrent, rate-limited)
Phase 3: Progressive supplementation for weak areas (convergence: L2 delta ≥ 20%)
Phase 4: MetricsCalculator → L1-L4 scores
Phase 5: DriftDetector → cross-model severity (none/low/moderate/high)
Phase 6: Reporter → Markdown + JSON reports
```

## Key Domain Concepts

- **SkillSpec**: Parsed skill model (name, triggers, workflow_steps, anti_patterns, output_format)
- **EvalCase**: Test case with category (normal/boundary/failure/trigger) + weighted assertions
- **L1-L4 Metrics**: Trigger accuracy / with-without delta / step adherence / stability (std dev)
- **Verdict**: PASS (all thresholds + drift none/low), PASS_WITH_CAVEATS (drift moderate), FAIL
- **Drift thresholds**: none ≤0.10, low ≤0.20, moderate ≤0.35, high >0.35
- **3 evaluation modes**: single (default), dialogue (multi-turn), replay (historical sessions)

## Module Details

See `engine/CLAUDE.md` and `adapters/CLAUDE.md` for module-level details.

## Data Flow

```
SKILL.md → analyzer(SkillSpec) → testgen(evals.json) → runner(with/without-skill results)
    → grader(assertion results) → metrics(L1-L4) → drift(severity) → reporter(md + json)
```

## Conventions

- Pydantic for all data models; functions return dicts via `model_dump(by_alias=True)`
- Prompt templates are `.md` files in `prompts/`, not Python strings
- JSON schemas in `schemas/` validate eval and SkillSpec structures
- Results per skill: `{name}-report.md`, `{name}-result.json`, `{name}-evals-cache.json`
- Config priority: CLI args > env vars > `~/.skill-cert/models.yaml` > defaults
- API keys via env vars only (SKILL_CERT_API_KEY, or per-model in config)

## Anti-Patterns (Project-Specific)

- Skip Phase 1 self-review loop (generate → review → gap-fill)
- Run with-skill without without-skill baseline
- Ignore L4 stability while focusing only on L2 delta
- Give PASS when drift severity is high
- Modify eval cases after Phase 2 execution begins (integrity rule)
- Use LLM-as-judge with temperature > 0

## Environment

- Python ≥3.10, pytest + ruff + black + isort
- WSL environment — watch for line ending issues
- `results/` contains pre-existing eval outputs from prior runs
