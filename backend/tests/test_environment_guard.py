"""W5 S-05: the environment guard must fail closed.

Two protections keyed off ``settings.environment`` — API docs suppression and
the ``EXPOSE_TOKENS_FOR_TESTING`` refusal — were both spelled
``== "production"`` against a free-form ``str``. Every other value therefore
read as "not production" and silently turned both off: ``ENVIRONMENT=prod``,
``=Production``, or unset entirely. Nothing raised, nothing logged, and the
deploy passed its healthcheck.

The tests that matter here are the *negative* ones. A test asserting that
``ENVIRONMENT=production`` blocks the flag passed against the old broken code
too, which is exactly why the bug survived. What has to be pinned is that
everything which is not development also blocks it.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings, assert_test_mode_allowed


# ---------------------------------------------------------------------------
# The Literal: a typo must not be silently accepted
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["prod", "Production", "PRODUCTION", "live", ""])
def test_unrecognised_environment_names_are_rejected_at_startup(bad, monkeypatch):
    """A misspelt ENVIRONMENT has to be a boot failure, not a quiet downgrade.

    Render, Fly and ECS all make ``prod`` the natural thing to type, and under
    the old free-form ``str`` that spelling disabled both protections while
    looking entirely healthy.
    """
    monkeypatch.setenv("ENVIRONMENT", bad)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://u:p@localhost/x")
    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.parametrize("good", ["development", "staging", "production"])
def test_the_three_real_environments_are_accepted(good, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", good)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://u:p@localhost/x")
    assert Settings().environment == good


# ---------------------------------------------------------------------------
# The flag guard: allowed in development only
# ---------------------------------------------------------------------------


def test_the_flag_is_allowed_in_development():
    assert_test_mode_allowed("development", expose_tokens=True)  # must not raise


@pytest.mark.parametrize("env", ["staging", "production"])
def test_the_flag_is_refused_everywhere_that_is_not_development(env):
    """Staging is the case the old check missed.

    A staging box is usually internet-reachable with real-ish data, and the
    flag mounts unauthenticated destructive endpoints, disables rate limiting
    and leaks confirmation tokens. ``!= "production"`` let all three through.
    """
    with pytest.raises(RuntimeError) as exc:
        assert_test_mode_allowed(env, expose_tokens=True)
    # The message must name the offending value — a guard that fires without
    # saying which environment tripped it costs an hour at deploy time.
    assert env in str(exc.value)


@pytest.mark.parametrize("env", ["development", "staging", "production"])
def test_no_environment_is_disturbed_when_the_flag_is_off(env):
    """The guard must be inert unless the flag is actually set, or every
    production boot fails."""
    assert_test_mode_allowed(env, expose_tokens=False)  # must not raise
