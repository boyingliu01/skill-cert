from abc import ABC, abstractmethod
from enum import Enum
from typing import Any


class ToolAvailability(str, Enum):
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class BaseIntegration(ABC):
    @abstractmethod
    def check_available(self) -> bool:
        ...

    @abstractmethod
    def get_version(self) -> str:
        ...

    @abstractmethod
    def run(self, spec: dict, **kwargs) -> dict:
        ...


class IntegrationDispatcher:
    def __init__(self):
        self._providers: list[BaseIntegration] = []

    def register(self, provider: BaseIntegration) -> None:
        self._providers.append(provider)

    def list_providers(self) -> list[BaseIntegration]:
        return list(self._providers)

    @property
    def registered_count(self) -> int:
        return len(self._providers)

    def health_check(self) -> dict[str, int]:
        available = 0
        unavailable = 0
        degraded = 0
        for provider in self._providers:
            if not provider.check_available():
                unavailable += 1
            elif hasattr(provider, "check_health"):
                status = getattr(provider, "check_health")()
                if status == ToolAvailability.DEGRADED:
                    degraded += 1
                else:
                    available += 1
            else:
                available += 1
        return {
            "available": available,
            "unavailable": unavailable,
            "degraded": degraded,
        }

    def run_all(self, spec: dict, **kwargs) -> list[dict]:
        results = []
        for provider in self._providers:
            if provider.check_available():
                results.append(provider.run(spec, **kwargs))
        return results


class SkillLabIntegration(BaseIntegration):
    def check_available(self) -> bool:
        try:
            import importlib
            importlib.import_module("skill_lab")
            return True
        except ImportError:
            return False

    def get_version(self) -> str:
        try:
            from skill_lab import __version__
            return __version__
        except ImportError:
            return "unavailable"

    def run(self, spec: dict, **kwargs) -> dict:
        if not self.check_available():
            return {"status": "skipped", "reason": "skill-lab not installed"}
        return {"status": "not_implemented", "tool": "skill-lab", "message": "integration pending"}


class DeepEvalIntegration(BaseIntegration):
    def check_available(self) -> bool:
        try:
            import importlib
            importlib.import_module("deepeval")
            return True
        except ImportError:
            return False

    def get_version(self) -> str:
        try:
            from deepeval import __version__
            return __version__
        except ImportError:
            return "unavailable"

    def run(self, spec: dict, **kwargs) -> dict:
        if not self.check_available():
            return {"status": "skipped", "reason": "deepeval not installed"}
        return {"status": "not_implemented", "tool": "deepeval", "message": "integration pending"}
