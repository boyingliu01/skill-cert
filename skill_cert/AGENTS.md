# skill_cert/ — CLI Entry Point

## OVERVIEW
Command-line interface for the skill-cert evaluation engine. Parses CLI arguments, validates config, orchestrates the full pipeline (parse → generate → execute → grade → report).

## STRUCTURE
```
skill_cert/
├── cli/
│   ├── main.py          # argparse surface + mode dispatch (single/dialogue/replay/stress/multi-skill)
│   ├── harness.py       # `skill-cert harness` — real-runtime double-run evaluation
│   ├── setup.py         # Interactive/non-interactive config wizard (skill-cert setup)
│   ├── evals.py         # Pipeline orchestration shared by mode handlers
│   ├── helpers.py       # Adapter construction, phase/metric printing, exit codes
│   ├── single.py / dialogue.py / replay.py / multi_skill.py / stress.py
│   └── __init__.py      # Package init, exports main()
└── __init__.py          # Package marker
```

## CLI FLAGS

| Flag | Purpose |
|------|---------|
| `--version` | Print version (read from installed package metadata) |
| `--skill` | Path to SKILL.md (can repeat for multi-skill) |
| `--models` | Model spec: `name=url,key\|name2=url,key` |
| `--models-alias` / `--fallback-model` | Alias table / fallback model |
| `--mode` | `single` (default), `dialogue`, `replay` |
| `--strict-schema` | Reject SKILL.md on required field violations |
| `--json-schema-validate` | Validate SKILL.md against the schema |
| `--with-skill-lab` | Enable SkillLab integration |
| `--with-deepeval` | Enable DeepEval integration |
| `--envelope` | Custom envelope thresholds as JSON |
| `--runs` | Multi-run count for L4 stability |
| `--max-turns` | Dialogue turn limit |
| `--session` | Replay session JSONL file |
| `--output` | Output directory (default: ./results) |
| `--format` | `markdown`, `json`, `both` |
| `--stress` / `--stress-concurrency` / `--stress-evals` | Concurrency stress testing |
| `--max-concurrency` / `--rate-limit-rpm` / `--request-timeout` | Transport limits |
| `--max-total-time` / `--token-budget` | Deadline + budget enforcement |
| `--no-llm-judge` / `--judge-samples` / `--debias-position` | Grading control |
| `--deep-security` | Extra security probes |
| `--calibration-set` | Golden eval set for calibration analysis |
| `--ci-history` / `--ci-history-path` | L4 CI-history source (default `.skill-cert-ci-history.json`) |
| `--trace-export` / `--trace-dir` / `--otlp-endpoint` | Telemetry export |

`skill-cert harness` has its own parser (`cli/harness.py`): `--skill`, `--harness opencode|dsh`,
`--model provider/model`, `--judge-model`, `--tasks`, `--runs`, `--output`, `--serve`,
`--task-timeout`, `--keep-sandboxes`.

## EXIT CODES
- 0: PASS
- 1: error (unhandled failure in `_run_with_error_handling`)
- 2: FAIL_WITH_CAVEATS

## CONVENTIONS
- argparse for CLI parsing (not click/typer)
- Lazy imports inside `main()` for test patching
- Progress feedback via print() to stderr
