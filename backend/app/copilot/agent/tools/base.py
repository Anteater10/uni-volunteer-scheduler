from dataclasses import dataclass
from typing import Any, Callable

from app.copilot.agent.boundary.role_scope import Scope


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    json_schema: dict[str, Any]
    allowed_roles: list[str]
    requires_confirmation: bool
    pii_schema: list[str]
    handler: Callable[[Any, Scope, dict[str, Any]], Any]
