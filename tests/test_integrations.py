"""Tests for engine/integrations.py — external tool integration framework."""
import pytest
from engine.integrations import (
    BaseIntegration,
    IntegrationDispatcher,
    ToolAvailability,
    SkillLabIntegration,
    DeepEvalIntegration,
)


class TestToolAvailability:
    def test_available_status(self):
        assert ToolAvailability.AVAILABLE.value == "available"

    def test_degraded_status(self):
        assert ToolAvailability.DEGRADED.value == "degraded"

    def test_unavailable_status(self):
        assert ToolAvailability.UNAVAILABLE.value == "unavailable"


class MockAvailableIntegration(BaseIntegration):
    def check_available(self):
        return True

    def get_version(self):
        return "1.0.0"

    def run(self, spec, **kwargs):
        return {"status": "ok", "tool": "mock-available"}


class MockUnavailableIntegration(BaseIntegration):
    def check_available(self):
        return False

    def get_version(self):
        return "0.0.0"

    def run(self, spec, **kwargs):
        return {"status": "unreachable"}


class MockDegradedIntegration(BaseIntegration):
    def __init__(self):
        self._available = True
        self._degraded = True

    def check_available(self):
        return self._available

    def check_health(self):
        from engine.integrations import ToolAvailability
        return ToolAvailability.DEGRADED if self._degraded else ToolAvailability.AVAILABLE

    def get_version(self):
        return "1.0.0-deprecated"

    def run(self, spec, **kwargs):
        return {"status": "partial", "warnings": ["version mismatch"]}


class TestBaseIntegration:
    def test_base_is_abstract(self):
        with pytest.raises(TypeError):
            BaseIntegration()

    def test_concrete_available_integration(self):
        integration = MockAvailableIntegration()
        assert integration.check_available() is True
        assert integration.get_version() == "1.0.0"

    def test_concrete_unavailable_integration(self):
        integration = MockUnavailableIntegration()
        assert integration.check_available() is False

    def test_run_returns_dict(self):
        integration = MockAvailableIntegration()
        result = integration.run(spec={"name": "test"})
        assert isinstance(result, dict)
        assert result["status"] == "ok"


class TestIntegrationDispatcher:
    def test_register_and_list_providers(self):
        dispatcher = IntegrationDispatcher()
        dispatcher.register(MockAvailableIntegration())
        assert len(dispatcher.list_providers()) == 1

    def test_run_all_with_available_providers(self):
        dispatcher = IntegrationDispatcher()
        dispatcher.register(MockAvailableIntegration())
        results = dispatcher.run_all(spec={})
        assert len(results) == 1
        assert results[0]["status"] == "ok"

    def test_run_all_skips_unavailable(self):
        dispatcher = IntegrationDispatcher()
        dispatcher.register(MockUnavailableIntegration())
        results = dispatcher.run_all(spec={})
        assert len(results) == 0

    def test_run_all_mixed_availability(self):
        dispatcher = IntegrationDispatcher()
        dispatcher.register(MockAvailableIntegration())
        dispatcher.register(MockUnavailableIntegration())
        results = dispatcher.run_all(spec={})
        assert len(results) == 1
        assert results[0]["status"] == "ok"

    def test_run_all_reports_skipped_count(self):
        dispatcher = IntegrationDispatcher()
        dispatcher.register(MockUnavailableIntegration())
        dispatcher.register(MockUnavailableIntegration())
        results = dispatcher.run_all(spec={})
        assert results == []

    def test_run_all_preserves_provider_order(self):
        dispatcher = IntegrationDispatcher()
        dispatcher.register(MockAvailableIntegration())
        dispatcher.register(MockDegradedIntegration())
        results = dispatcher.run_all(spec={})
        assert len(results) == 2
        assert results[0]["tool"] == "mock-available"
        assert results[1]["status"] == "partial"

    def test_health_check_all_available(self):
        dispatcher = IntegrationDispatcher()
        dispatcher.register(MockAvailableIntegration())
        health = dispatcher.health_check()
        assert health["available"] == 1
        assert health["unavailable"] == 0
        assert health["degraded"] == 0

    def test_health_check_unavailable(self):
        dispatcher = IntegrationDispatcher()
        dispatcher.register(MockUnavailableIntegration())
        health = dispatcher.health_check()
        assert health["available"] == 0
        assert health["unavailable"] == 1

    def test_health_check_mixed(self):
        dispatcher = IntegrationDispatcher()
        dispatcher.register(MockAvailableIntegration())
        dispatcher.register(MockDegradedIntegration())
        dispatcher.register(MockUnavailableIntegration())
        health = dispatcher.health_check()
        assert health["available"] == 1
        assert health["unavailable"] == 1
        assert health["degraded"] == 1

    def test_registered_count(self):
        dispatcher = IntegrationDispatcher()
        assert dispatcher.registered_count == 0
        dispatcher.register(MockAvailableIntegration())
        assert dispatcher.registered_count == 1


class TestSkillLabIntegration:
    def test_skill_lab_is_concrete_integration(self):
        assert issubclass(SkillLabIntegration, BaseIntegration)

    def test_skill_lab_check_available_returns_bool(self):
        integration = SkillLabIntegration()
        result = integration.check_available()
        assert isinstance(result, bool)

    def test_skill_lab_get_version_returns_string(self):
        integration = SkillLabIntegration()
        version = integration.get_version()
        assert isinstance(version, str)

    def test_skill_lab_run_returns_dict(self):
        integration = SkillLabIntegration()
        result = integration.run(spec={"name": "test-skill", "path": "/tmp"})
        assert isinstance(result, dict)


class TestDeepEvalIntegration:
    def test_deepeval_is_concrete_integration(self):
        assert issubclass(DeepEvalIntegration, BaseIntegration)

    def test_deepeval_check_available_returns_bool(self):
        integration = DeepEvalIntegration()
        result = integration.check_available()
        assert isinstance(result, bool)

    def test_deepeval_get_version_returns_string(self):
        integration = DeepEvalIntegration()
        version = integration.get_version()
        assert isinstance(version, str)

    def test_deepeval_run_returns_dict(self):
        integration = DeepEvalIntegration()
        result = integration.run(spec={"name": "test-skill"})
        assert isinstance(result, dict)
