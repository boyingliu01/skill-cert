# Skill Design Specification Template

Use this template when creating or refactoring any AI Skill. Ensures consistent quality and machine-verifiable output.

## 1. Metadata

```yaml
---
name: skill-name
description: One sentence describing WHEN to trigger this skill
triggers:
  - "trigger phrase 1"
  - "trigger phrase 2"
  - "触发短语"
---
```

## 2. Input Contract

Define what the skill expects from the user or context.

```markdown
## Input Contract
- **Required**: [What must be provided]
- **Optional**: [What can be omitted]
- **Context**: [Files, environment, or state needed]
```

## 3. Workflow

Define steps as atomic, verifiable actions. Each step MUST produce a specific output.

```markdown
## Workflow
1. **[Step Name]** → Output: [Specific deliverable format]
2. **[Step Name]** → Output: [Specific deliverable format]
3. **[Step Name]** → Output: [Specific deliverable format]
```

## 4. Output Contract (MANDATORY)

Every skill MUST define its output as valid JSON schema or machine-readable tokens.

```markdown
## Output Format (MANDATORY)
Output MUST be valid JSON matching this structure:

```json
{
  "field_name": "type",
  "status": "PASS|FAIL|BLOCKED",
  "nested": {"key": "value"},
  "metrics": {"score": 0.85}
}
```

**Eval assertions check for:** `field_name`, `status`, `metrics.score`.
```

## 5. Anti-Patterns

List what the skill MUST NOT do. Each anti-pattern should map to a test case.

```markdown
## Anti-Patterns
| Pattern | Expected Behavior | Assertion |
|---------|------------------|-----------|
| [What not to do] | [How skill should handle it] | `not_contains` / `regex` |
```

## 6. Token Budget

Estimate token usage to optimize SKILL.md size and API costs.

```markdown
## Token Budget
- Max input tokens: ~1500 (after optimization)
- Max output tokens: ~4000
- Optimization: Remove verbose examples, use concise tables
```

---

## Example: Minimal Viable Skill

```markdown
---
name: code-review
description: "Review code for quality and security issues. Trigger: 'review this PR', 'code review'"
---

# Code Review

## Workflow
1. **Analyze Changes** → Output: List of files and line ranges
2. **Check Patterns** → Output: Violations with severity
3. **Generate Report** → Output: JSON summary

## Output Format (MANDATORY)
```json
{
  "review_status": "APPROVED|CHANGES_REQUESTED",
  "violations": [{"file": "string", "line": "number", "severity": "critical|major|minor"}],
  "summary": "string"
}
```

## Anti-Patterns
| Pattern | Expected Behavior |
|---------|------------------|
| Skip security checks | Must always check for injection/leaks |
| Ignore critical issues | Must BLOCK if critical found |
```
