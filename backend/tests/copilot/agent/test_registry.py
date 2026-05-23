import pytest

from app.copilot.agent.tools import registry
from app.copilot.agent.tools.base import Tool


def test_register_then_lookup_by_name():
    t = Tool(
        name="t1",
        description="",
        json_schema={},
        allowed_roles=["admin"],
        requires_confirmation=False,
        pii_schema=[],
        handler=lambda db, scope, args: {"ok": True},
    )
    registry.register(t)
    assert registry.get_tool("t1") is t


def test_get_tools_for_admin_includes_admin_only():
    admin_tool = Tool(
        name="a1",
        description="",
        json_schema={},
        allowed_roles=["admin"],
        requires_confirmation=False,
        pii_schema=[],
        handler=lambda *_: {},
    )
    organizer_tool = Tool(
        name="o1",
        description="",
        json_schema={},
        allowed_roles=["admin", "organizer"],
        requires_confirmation=False,
        pii_schema=[],
        handler=lambda *_: {},
    )
    registry.register(admin_tool)
    registry.register(organizer_tool)
    admin_tools = registry.get_tools_for_role("admin")
    assert any(t.name == "a1" for t in admin_tools)
    assert any(t.name == "o1" for t in admin_tools)


def test_get_tools_for_organizer_excludes_admin_only():
    admin_tool = Tool(
        name="a1",
        description="",
        json_schema={},
        allowed_roles=["admin"],
        requires_confirmation=False,
        pii_schema=[],
        handler=lambda *_: {},
    )
    organizer_tool = Tool(
        name="o1",
        description="",
        json_schema={},
        allowed_roles=["admin", "organizer"],
        requires_confirmation=False,
        pii_schema=[],
        handler=lambda *_: {},
    )
    registry.register(admin_tool)
    registry.register(organizer_tool)
    tools = registry.get_tools_for_role("organizer")
    assert not any(t.name == "a1" for t in tools)
    assert any(t.name == "o1" for t in tools)


def test_register_duplicate_raises():
    t = Tool(
        name="t1",
        description="",
        json_schema={},
        allowed_roles=[],
        requires_confirmation=False,
        pii_schema=[],
        handler=lambda *_: {},
    )
    registry.register(t)
    with pytest.raises(ValueError):
        registry.register(
            Tool(
                name="t1",
                description="",
                json_schema={},
                allowed_roles=[],
                requires_confirmation=False,
                pii_schema=[],
                handler=lambda *_: {},
            )
        )
