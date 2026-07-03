"""Tests for integration dispatcher graceful degradation."""

from engine.integrations import (
    BaseIntegration,
    GiskardSecurityIntegration,
    IntegrationDispatcher,
    PromptfooSecurityIntegration,
    ToolAvailability,
)


class AlwaysFailingIntegration(BaseIntegration):
    """Mock integration that simulates an unavailable tool."""

    def check_available(self):
        return False

    def get_version(self):
        return "unavailable"

    def run(self, spec, **kwargs):
        return {"status": "skipped"}


def test_dispatcher_graceful_degradation():
    """When all providers are unavailable, dispatcher should not crash."""
    dispatcher = IntegrationDispatcher()
    dispatcher.register(AlwaysFailingIntegration())
    dispatcher.register(GiskardSecurityIntegration())
    dispatcher.register(PromptfooSecurityIntegration())

    health = dispatcher.health_check()
    assert "available" in health
    assert "unavailable" in health
    assert "degraded" in health
    total = health["available"] + health["unavailable"] + health["degraded"]
    assert total == 3  # Three providers registered


def test_dispatcher_run_all_skips_unavailable():
    """dispatcher.run_all skips unavailable providers without crashing."""
    dispatcher = IntegrationDispatcher()
    dispatcher.register(AlwaysFailingIntegration())

    results = dispatcher.run_all({"skill_content": "print('hello')"})
    assert isinstance(results, list)


def test_dispatcher_empty_graceful():
    """Dispatcher with no registered providers handles run_all gracefully."""
    dispatcher = IntegrationDispatcher()
    results = dispatcher.run_all({"test": True})
    assert results == []


def test_dispatcher_health_status_enum():
    """ToolAvailability enum has expected values."""
    assert ToolAvailability.AVAILABLE.value == "available"
    assert ToolAvailability.DEGRADED.value == "degraded"
    assert ToolAvailability.UNAVAILABLE.value == "unavailable"
