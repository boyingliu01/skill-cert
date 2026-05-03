"""SKILL.md parser — extracts structured semantic model from markdown skill files."""

import re
from pathlib import Path

from markdown_it import MarkdownIt
from pydantic import BaseModel, Field


class WorkflowStep(BaseModel):
    name: str
    step_type: str = Field(alias="type", default="unknown")
    critical: bool = False


class SkillSpec(BaseModel):
    name: str
    description: str = ""
    triggers: list[str] = Field(default_factory=list)
    workflow_steps: list[WorkflowStep] = Field(default_factory=list)
    anti_patterns: list[str] = Field(default_factory=list)
    output_format: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    content_length: int = 0
    parse_method: str = "regex"
    parse_confidence: float = 0.0


class SchemaViolation:
    def __init__(self, field: str, reason: str):
        self.field = field
        self.reason = reason

    def __repr__(self):
        return f"SchemaViolation(field='{self.field}', reason='{self.reason}')"


class SchemaValidationResult:
    def __init__(self, violations: list, confidence_penalty: float = 0.0):
        self.violations = violations
        self.confidence_penalty = confidence_penalty

    @property
    def is_valid(self) -> bool:
        return len(self.violations) == 0


MAX_DESCRIPTION_LENGTH = 500
FLOW_LANGUAGE_PATTERNS = [
    r"\bstep\s+\d+", r"\bfirst\s*[,\s]+\s*then\b", r"\bafter that\b",
    r"\bnext\s*[,\s]+\s*you\b", r"\bworkflow\b", r"\bfollow\s+these\s+steps\b",
]


def _validate_schema(spec: SkillSpec, raw_content: str) -> SchemaValidationResult:
    """Validate SKILL.md schema. Penalties are format-agnostic — only apply
    for interactive/security-sensitive skills that declare them."""
    violations = []
    confidence_penalty = 0.0

    is_interactive = any(m in raw_content.lower() for m in (
        "interactive", "askuserquestion", "bypass", "dangerous_cmd",
        "rm -f", "rm -rf", "git rm", "shell", "bash", "preamble"
    ))
    has_security_section = _section_exists(raw_content, "Security Notes")
    has_permissions_section = _section_exists(raw_content, "Permissions")

    # Security/Permissions: only penalize for interactive skills
    if is_interactive and not has_security_section:
        violations.append(SchemaViolation("security_notes", "section missing or empty"))
        confidence_penalty += 0.15
    if is_interactive and not has_permissions_section:
        violations.append(SchemaViolation("permissions", "section missing or empty"))
        confidence_penalty += 0.15

    has_scope, scope_has_does_not = _scope_check(raw_content)
    if not has_scope:
        violations.append(SchemaViolation("scope", "section missing"))
        confidence_penalty += 0.10
    elif not scope_has_does_not:
        violations.append(SchemaViolation("scope", "missing 'Does NOT' clause"))
        confidence_penalty += 0.10

    if len(spec.description) > MAX_DESCRIPTION_LENGTH:
        violations.append(SchemaViolation(
            "description", f"exceeds {MAX_DESCRIPTION_LENGTH} characters ({len(spec.description)})"
        ))
        confidence_penalty += 0.05

    if _has_flow_language(spec.description):
        violations.append(SchemaViolation(
            "description", "contains workflow/step-by-step language — should describe what, not how"
        ))
        confidence_penalty += 0.10

    return SchemaValidationResult(violations=violations, confidence_penalty=round(confidence_penalty, 2))


def _section_exists(content: str, section_name: str) -> bool:
    pattern = rf"^##\s+{re.escape(section_name)}\s*$(.+?)(?=^##\s|\Z)"
    match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
    if not match:
        return False
    body = match.group(1).strip()
    return len(body) > 0


def _scope_check(content: str) -> tuple:
    has_scope = _section_exists(content, "Scope")
    if not has_scope:
        return False, False
    pattern = r"^##\s+Scope\s*$(.+?)(?=^##\s|\Z)"
    match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
    body = match.group(1).strip().lower() if match else ""
    has_does_not = "does not" in body
    return True, has_does_not


def _has_flow_language(text: str) -> bool:
    for pattern in FLOW_LANGUAGE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def parse_skill_md(file_path: str) -> dict:
    """Parse a SKILL.md file and return structured SkillSpec as dict."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"SKILL.md not found: {file_path}")

    content = path.read_text(encoding="utf-8")
    spec = SkillSpec(name="unknown", content_length=len(content))

    # Step 1: Extract YAML frontmatter
    frontmatter = _extract_frontmatter(content)
    if frontmatter:
        spec.name = frontmatter.get("name", "unknown")
        spec.description = frontmatter.get("description", "")
    else:
        # Fallback: extract name from first heading
        heading_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if heading_match:
            spec.name = heading_match.group(1).strip().lower().replace(" ", "-")

    # Step 2: AST-based structure validation with markdown-it-py
    md = MarkdownIt("commonmark")
    tokens = md.parse(content)
    headings = _extract_headings(tokens)

    # Step 3: Regex extraction of key sections
    workflow_steps = _extract_workflow_steps(content)
    anti_patterns = _extract_anti_patterns(content)
    output_format = _extract_output_format(content)
    triggers = _extract_triggers(content, spec.description, frontmatter)
    examples = _extract_examples(content)

    spec.workflow_steps = workflow_steps
    spec.anti_patterns = anti_patterns
    spec.output_format = output_format
    spec.triggers = triggers
    spec.examples = examples

    # Step 4: Calculate parse confidence
    spec.parse_confidence = _calculate_confidence(
        has_frontmatter=bool(frontmatter),
        has_workflow=bool(workflow_steps),
        has_headings=bool(headings),
        has_anti_patterns=bool(anti_patterns),
        has_output_format=bool(output_format),
        has_examples=bool(examples),
        has_triggers=bool(triggers),
        content_length=len(content),
    )

    # Step 5: Schema validation (REQ-P0-002)
    schema_result = _validate_schema(spec, content)
    spec.parse_confidence = max(0.0, spec.parse_confidence - schema_result.confidence_penalty)

    # Step 6: Determine parse method
    if spec.parse_confidence >= 0.6 and frontmatter:
        spec.parse_method = "regex"
    else:
        spec.parse_method = "hybrid"  # Would fallback to LLM in production

    result = spec.model_dump(by_alias=True)
    result["schema_validation"] = {
        "is_valid": schema_result.is_valid,
        "violations": [{"field": v.field, "reason": v.reason} for v in schema_result.violations],
        "confidence_penalty": schema_result.confidence_penalty,
    }

    return result


def _extract_frontmatter(content: str) -> dict | None:
    """Extract YAML frontmatter between --- delimiters."""
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return None
    result = {}
    current_key = None
    current_list = None
    for line in match.group(1).split("\n"):
        # List item: "  - value"
        if line.startswith("  - ") and current_key:
            if current_list is None:
                current_list = []
                result[current_key] = current_list
            current_list.append(line[4:].strip())
            continue
        # Key-value: "key: value"
        if ":" in line and not line.startswith(" "):
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if value:
                result[key] = value
                current_key = None
                current_list = None
            else:
                # List placeholder: "key:"
                current_key = key
                current_list = None
        elif line.strip() == "" and current_key:
            # Blank line — finalize current list
            current_key = None
            current_list = None
    return result


def _extract_headings(tokens: list) -> list[dict]:
    """Extract headings from markdown-it-py tokens for AST validation."""
    return [
        {"level": t.tag.replace("h", ""), "content": t.content}
        for t in tokens
        if t.type == "heading_open"
    ]


def _extract_workflow_steps(content: str) -> list[WorkflowStep]:
    """Extract workflow steps from ## Workflow/Process/Flow sections.
    Supports English and Chinese section names, numbered lists,
    and Phase N: NAME patterns in ASCII diagrams.
    """
    pattern = r"^##\s+[^#\n]*(?:Workflow|Process|Flow|完整流程|核心流程|流程|步骤|工作流程)[^\n]*$\n(.*?)(?=^##\s|\Z)"
    match = re.search(pattern, content, re.IGNORECASE | re.DOTALL | re.MULTILINE)
    if not match:
        return []

    section = match.group(1)
    steps = []
    seen = set()

    for line in section.split("\n"):
        stripped = line.strip()
        # Numbered list: "1. Step name" or "- Step name"
        m = re.match(r"^(?:\d+\.|-)\s+(.+)$", stripped)
        if m:
            name = m.group(1).strip()
            if name and name not in seen:
                steps.append(WorkflowStep(name=name, step_type="unknown", critical=False))
                seen.add(name)
            continue
        # Phase pattern: "Phase 0: NAME" or "Phase N: ..."
        m = re.match(r"^Phase\s+(\d+):\s*(\S+)", stripped)
        if m:
            phase_num = m.group(1)
            phase_name = m.group(2).strip().rstrip("→").strip()
            entry = f"Phase {phase_num}: {phase_name}"
            if entry not in seen:
                steps.append(WorkflowStep(name=entry, step_type="phase", critical=False))
                seen.add(entry)
    return steps


def _extract_anti_patterns(content: str) -> list[str]:
    """Extract anti-patterns from ## Anti-Patterns sections."""
    pattern = r"##\s+Anti-Patterns\s*\n(.*?)(?=##\s|\Z)"
    match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
    if not match:
        return []

    section = match.group(1)
    patterns = []
    for line in section.split("\n"):
        line = line.strip()
        if line.startswith("|") and "---" not in line:
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if not parts:
                continue
            # Skip table header rows
            first = parts[0].lower()
            if first in ("pattern", "pattern/anti-pattern", "anti-pattern", "❌ 错误", "错误", "anti-pattern/错误"):
                continue
            patterns.append(parts[0])
    return patterns


def _of_parse_json_keys(line: str, in_json: bool) -> tuple[list[str], bool]:
    """Parse JSON key from line inside a code block. Returns (keys, in_json_state)."""
    stripped = line.strip()
    if stripped.startswith("```"):
        return [], not in_json
    if not in_json:
        return [], in_json
    m = re.match(r'\s*"(\w+)"\s*:', stripped)
    if m:
        return [m.group(1)], in_json
    return [], in_json


def _of_parse_list_item(line: str) -> str | None:
    """Extract list item from '- item' or '* item' lines."""
    m = re.match(r"^[-*]\s+(\S.+)$", line.strip())
    if m:
        item = m.group(1).strip()
        if len(item) > 2:
            return item
    return None


def _of_parse_assertion_line(line: str) -> list[str]:
    """Extract field names from 'assertions check for: `field1`, `field2`' lines."""
    if "assertions check for" not in line.lower():
        return []
    m = re.search(r"check for:\s*[`']([^`'\n]+)[`']", line)
    if not m:
        return []
    raw = m.group(1)
    return [x for x in (s.strip().strip("`").strip("'").strip() for s in raw.split(",")) if len(x) > 1]


def _of_filter_noise(outputs: list[str]) -> list[str]:
    """Remove markdown artifacts and anti-pattern assertion lines from output items."""
    noise = {"", "-", "--", "**", "---", "..."}
    ap_assertion_re = re.compile(r"→\s*Output\s+MUST", re.IGNORECASE)
    return [
        o for o in outputs
        if o not in noise and not o.startswith("**") and not ap_assertion_re.search(o)
    ]


def _extract_output_format(content: str) -> list[str]:
    """Extract output format from ## Output Format sections."""
    pattern = r"^##\s+Output Format[^\n]*$\n(.*?)(?=^##\s|\Z)"
    match = re.search(pattern, content, re.IGNORECASE | re.DOTALL | re.MULTILINE)
    if not match:
        return []

    section = match.group(1)
    outputs: list[str] = []
    in_json = False
    for line in section.split("\n"):
        keys, in_json = _of_parse_json_keys(line, in_json)
        for k in keys:
            if k not in outputs:
                outputs.append(k)
        if not in_json:
            item = _of_parse_list_item(line)
            if item and item not in outputs:
                outputs.append(item)
        for field in _of_parse_assertion_line(line):
            if field not in outputs:
                outputs.append(field)
    return _of_filter_noise(outputs)


def _extract_triggers_from_frontmatter(content: str) -> list[str]:
    """Extract TRIGGER items from raw frontmatter block (handles folded YAML)."""
    triggers = []
    fm_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not fm_match:
        return triggers
    fm_block = fm_match.group(1)
    trigger_section = re.search(
        r"(?:^|\n)\s*TRIGGER\s*:\s*\n((?:\s*-.*\n?)*)",
        fm_block, re.IGNORECASE
    )
    if trigger_section:
        for line in trigger_section.group(1).split("\n"):
            line = line.strip().strip("-").strip().strip('"').strip("'")
            if line and len(line) > 1:
                triggers.append(line)
    return triggers


def _extract_triggers_from_body(content: str) -> list[str]:
    """Extract triggers from ## Triggers section in body."""
    triggers = []
    pattern = r"^##\s+(?:Triggers|TRIGGER|触发条件|触发)[^\n]*$\n(.*?)(?=^##\s|\Z)"
    match = re.search(pattern, content, re.IGNORECASE | re.DOTALL | re.MULTILINE)
    if match:
        for line in match.group(1).split("\n"):
            line = line.strip().strip("-").strip()
            if line and not line.startswith("#"):
                triggers.append(line)
    return triggers


def _extract_triggers(content: str, description: str, frontmatter: dict | None) -> list[str]:
    """Extract trigger keywords from frontmatter, TRIGGER section, and description."""
    triggers = []

    # 1. Frontmatter TRIGGER/TRIGGERS field
    if frontmatter:
        trigger_val = frontmatter.get("triggers") or frontmatter.get("TRIGGERS") or frontmatter.get("TRIGGER")
        if isinstance(trigger_val, str):
            triggers.extend([t.strip() for t in trigger_val.split(",") if t.strip()])
        elif isinstance(trigger_val, list):
            triggers.extend([str(t).strip() for t in trigger_val if str(t).strip()])

    # 2. Raw frontmatter block (folded YAML)
    triggers.extend(_extract_triggers_from_frontmatter(content))

    # 3. Body TRIGGERS section
    triggers.extend(_extract_triggers_from_body(content))

    # 4. Fallback: action verbs from description
    if not triggers and description:
        verbs = re.findall(r"\b(\w+)\s+(this|the|a|an)\b", description.lower())
        triggers.extend([v[0] for v in verbs])

    return list(set(triggers))


def _extract_examples(content: str) -> list[str]:
    """Extract examples from ## Examples sections."""
    pattern = r"##\s+Examples?\s*\n(.*?)(?=##\s|\Z)"
    match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
    if not match:
        return []

    section = match.group(1)
    examples = []
    for line in section.split("\n"):
        line = line.strip()
        if line.startswith("-") or line.startswith("*"):
            examples.append(line[1:].strip())
    return examples


def _calculate_confidence(
    has_frontmatter: bool,
    has_workflow: bool,
    has_headings: bool,
    has_anti_patterns: bool = False,
    has_output_format: bool = False,
    has_examples: bool = False,
    has_triggers: bool = False,
    content_length: int = 0,
) -> float:
    """Calculate parse confidence based on extracted fields."""
    score = 0.0
    if has_frontmatter:
        score += 0.3
    if has_workflow:
        score += 0.25
    if has_headings:
        score += 0.15
    if has_anti_patterns:
        score += 0.1
    if has_output_format:
        score += 0.08
    if has_triggers:
        score += 0.07
    if has_examples:
        score += 0.05
    if content_length > 0 and content_length // 40 >= 5:
        score += 0.05
    return min(score, 1.0)
