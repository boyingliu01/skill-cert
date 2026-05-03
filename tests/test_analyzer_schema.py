from engine.analyzer import parse_skill_md, SkillSpec, _validate_schema, SchemaValidationResult
from engine.analyzer import SchemaViolation


class TestSchemaValidationResult:
    def test_valid_spec_no_violations(self):
        result = SchemaValidationResult(violations=[], confidence_penalty=0.0)
        assert result.is_valid is True
        assert result.confidence_penalty == 0.0

    def test_violations_make_invalid(self):
        v = SchemaViolation(field="permissions", reason="missing")
        result = SchemaValidationResult(violations=[v], confidence_penalty=0.15)
        assert result.is_valid is False
        assert len(result.violations) == 1

    def test_multiple_violations(self):
        v1 = SchemaViolation(field="permissions", reason="missing")
        v2 = SchemaViolation(field="scope", reason="missing")
        result = SchemaValidationResult(violations=[v1, v2], confidence_penalty=0.25)
        assert result.is_valid is False
        assert result.confidence_penalty == 0.25


class TestSchemaViolation:
    def test_violation_fields(self):
        v = SchemaViolation(field="security_notes", reason="section missing or empty")
        assert v.field == "security_notes"
        assert v.reason == "section missing or empty"

    def test_violation_repr(self):
        v = SchemaViolation(field="description", reason="exceeds 500 chars")
        assert "description" in repr(v)
        assert "exceeds 500 chars" in repr(v)


class TestValidateSchema:
    def setup_method(self):
        import tempfile
        import os
        self.tmpdir = tempfile.mkdtemp()

    def _write_skill(self, name, content):
        import os
        path = os.path.join(self.tmpdir, name)
        with open(path, "w") as f:
            f.write(content)
        return path

    def test_validate_with_all_required_sections(self):
        content = """---
name: test-skill
description: A test skill for unit testing
---

## Security Notes
This skill does not handle sensitive data.

## Permissions
- Read files in workspace
- Execute shell commands

## Scope
This skill handles test file generation. Does NOT modify production code.
"""
        spec = SkillSpec(name="test", description="A test skill for unit testing")
        result = _validate_schema(spec, content)
        assert result.is_valid is True

    def test_validate_missing_security_notes(self):
        content = """---
name: test-skill
description: short description
---

AskUserQuestion for permissions.

## Permissions
- Read files

## Scope
Test scope. Does NOT modify production.
"""
        spec = SkillSpec(name="test", description="short description")
        result = _validate_schema(spec, content)
        assert result.is_valid is False
        assert any(v.field == "security_notes" for v in result.violations)
        assert result.confidence_penalty >= 0.15

    def test_validate_missing_permissions(self):
        content = """---
name: test-skill
description: short description
---

AskUserQuestion for security.

## Security Notes
No sensitive data.

## Scope
Test scope. Does NOT modify production.
"""
        spec = SkillSpec(name="test", description="short description")
        result = _validate_schema(spec, content)
        assert any(v.field == "permissions" for v in result.violations)

    def test_validate_missing_scope(self):
        content = """---
name: test-skill
description: short description
---

## Security Notes
No sensitive data.

## Permissions
- Read files
"""
        spec = SkillSpec(name="test", description="short description")
        result = _validate_schema(spec, content)
        assert any(v.field == "scope" for v in result.violations)

    def test_validate_scope_missing_does_not_clause(self):
        content = """---
name: test-skill
description: short description
---

## Security Notes
No sensitive data.

## Permissions
- Read files

## Scope
Handles file generation.
"""
        spec = SkillSpec(name="test", description="short description")
        result = _validate_schema(spec, content)
        assert any(v.field == "scope" for v in result.violations)

    def test_validate_description_too_long(self):
        long_desc = "x" * 501
        content = f"""---
name: test-skill
description: {long_desc}
---

## Security Notes
No sensitive data.

## Permissions
- Read files

## Scope
Test scope. Does NOT modify production.
"""
        spec = SkillSpec(name="test", description=long_desc)
        result = _validate_schema(spec, content)
        assert any(v.field == "description" for v in result.violations)

    def test_validate_description_contains_flow_language(self):
        content = """---
name: test-skill
description: Short desc but this step-by-step workflow will: first do X, then do Y
---

## Security Notes
No sensitive data.

## Permissions
- Read files

## Scope
Test scope. Does NOT modify production.
"""
        spec = SkillSpec(name="test", description="Short desc but this step-by-step workflow will: first do X, then do Y")
        result = _validate_schema(spec, content)
        assert any(
            v.field == "description" and "workflow" in v.reason.lower()
            for v in result.violations
        )

    def test_validate_empty_security_notes(self):
        content = """---
name: test-skill
description: short description
---

Uses AskUserQuestion.

## Security Notes


## Permissions
- Read files

## Scope
Test scope. Does NOT modify production.
"""
        spec = SkillSpec(name="test", description="short description")
        result = _validate_schema(spec, content)
        assert any(
            v.field == "security_notes" and "empty" in v.reason.lower()
            for v in result.violations
        )

    def test_validate_all_fields_present_is_valid(self):
        content = """---
name: test-skill
description: A concise description of what this skill does
---

## Security Notes
This skill only reads workspace files. No network access. No credential handling.

## Permissions
- Read files from workspace directory
- Execute shell commands within project root only

## Scope
This skill handles automated code review for Python files.
Does NOT handle production deployments, database migrations, or security audits.
"""
        spec = SkillSpec(name="test", description="A concise description of what this skill does")
        result = _validate_schema(spec, content)
        assert result.is_valid is True
        assert result.confidence_penalty == 0.0

    def test_confidence_penalty_accumulation(self):
        content = """---
name: test-skill
description: x
---

Uses AskUserQuestion and rm -rf for cleanup.

## Foo
bar
"""
        spec = SkillSpec(name="test", description="x")
        result = _validate_schema(spec, content)
        # Interactive skill missing: security_notes(0.15) + permissions(0.15) + scope(0.10) = 0.40
        assert result.confidence_penalty >= 0.40

    def test_parse_skill_md_includes_validation(self):
        path = self._write_skill("SKILL.md", """---
name: test-skill
description: A test skill
---

## Security Notes
No sensitive data.

## Permissions
- Read files

## Scope
Test scope. Does NOT modify production.
""")
        result = parse_skill_md(path)
        assert "schema_validation" in result
