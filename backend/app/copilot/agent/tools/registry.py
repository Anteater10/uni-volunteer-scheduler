from app.copilot.agent.tools.base import Tool

_REGISTRY: dict[str, Tool] = {}


def register(tool: Tool) -> None:
    if tool.name in _REGISTRY:
        raise ValueError(f"tool {tool.name!r} already registered")
    _REGISTRY[tool.name] = tool


def get_tool(name: str) -> Tool:
    return _REGISTRY[name]


def get_tools_for_role(role: str) -> list[Tool]:
    return [t for t in _REGISTRY.values() if role in t.allowed_roles]


def _reset_for_tests() -> None:
    _REGISTRY.clear()
