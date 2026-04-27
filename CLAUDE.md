
## Critical Rules (from UAT experience)

### API Operations
1. **Verify endpoint compatibility FIRST** — Test with 1 simple call before any batch operation. Different providers use different compatible endpoints (OpenAI vs Anthropic). A 401 on batch start wastes 30+ minutes.
2. **Test 1 end-to-end case FIRST** — Before running batch eval cases, verify complete flow: parse → generate → execute 1 → grade → metrics → report. Catches interface mismatches early.
3. **Cache all LLM results** — Cache eval cases to `results/{skill}-evals-cache.json`. LLM generation is expensive (40s+) and deterministic with temperature=0. Never regenerate if cache exists.

### Skill Design
4. **Define Output Contract** — Every SKILL.md MUST have an `## Output Format` section with explicit JSON schema. Without it, eval assertions fail (model outputs natural language, assertions expect machine-readable tokens).
5. **Match assertions to output** — Eval assertions must check for tokens/fields that actually exist in the defined output format, not arbitrary keywords.

### Git Operations
6. **Isolate subproject repos** — When developing skill-cert within xgate, NEVER `git add -A` from subproject directory. It captures entire parent repo history. Always initialize separate git repo in isolated directory.

### Code Quality
7. **Unify field naming across pipeline** — grader.py → metrics.py → reporter.py must use consistent field names. Add integration test verifying end-to-end metric flow before each release.
