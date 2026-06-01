# skill_cert/ — CLI Entry Point

## OVERVIEW
Command-line interface for the skill-cert evaluation engine. Parses CLI arguments, validates config, orchestrates the full pipeline (parse → generate → execute → grade → report).

## STRUCTURE
```
skill_cert/
├── cli.py             # Main CLI: argparse-based, all pipeline orchestration
└── __init__.py        # Package marker
```

## WHERE TO LOOK
| Task | File | Notes |
|------|------|-------|
| CLI argument parsing | `cli.py` | --skill, --models, --output, --mode, --runs, --max-turns, --session |
| Pipeline orchestration | `cli.py` | Calls engine/ modules in sequence |
| Model string parsing | `cli.py` | "name=url,key" format with pipe separator for multi-model |
| Exit codes | `cli.py` | 0=PASS, 1=FAIL, 2=error |

## CONVENTIONS
- argparse for CLI parsing (not click/typer)
- All engine imports at module level
- Progress feedback via print() to stderr
- Exit codes: 0 (PASS), 1 (FAIL), 2 (error)

## NOTES
- cli.py is the lowest-coverage module (35%) — needs more integration tests
- Model strings use format: "name=base_url,api_key" with | separator for multiple models
