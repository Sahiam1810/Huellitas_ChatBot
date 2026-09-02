from typing import TypedDict

from app.orchestration.module_executor import ModuleExecutionRequest, ModuleResult


class ServicesCatalogGraphState(TypedDict, total=False):
    request: ModuleExecutionRequest
    result: ModuleResult
