# skill_cert/ — CLI Entry Point

## OVERVIEW
Command-line interface for the skill-cert evaluation engine. Parses CLI arguments, validates config, orchestrates the full pipeline (parse → generate → execute → grade → report).

## STRUCTURE
```
skill_cert/
├── cli/
│   ├── main.py          # Main CLI: argparse-based, all pipeline orchestration
│   ├── setup.py         # Interactive/non-interactive config wizard (skill-cert setup)
│   └── __init__.py      # Package init, exports main()
└── __init__.py          # Package marker
```

## CLI FLAGS

| Flag | Purpose |
|------|---------|
| `--version` | Print version |
| `--skill` | Path to SKILL.md (can repeat for multi-skill) |
| `--models` | Model spec: `name=url,key\|name2=url,key` |
| `--mode` | `single` (default), `dialogue`, `replay` |
| `--strict-schema` | Reject SKILL.md on required field violations |
| `--with-skill-lab` | Enable SkillLab integration |
| `--with-deepeval` | Enable DeepEval integration |
| `--envelope` | Custom envelope thresholds as JSON |
| `--runs` | Multi-run count for L4 stability |
| `--max-turns` | Dialogue turn limit |
| `--session` | Replay session JSONL file |
| `--output` | Output directory (default: ./results) |

## EXIT CODES
- 0: PASS
- 1: FAIL
- 2: error

## CONVENTIONS
- argparse for CLI parsing (not click/typer)
- Lazy imports inside `main()` for test patching
- Progress feedback via print() to stderr
