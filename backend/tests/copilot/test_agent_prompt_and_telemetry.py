"""K23, K29, K30 — what the agent path tells the rest of the system.

Three separate defects that all came down to the agent loop not reporting
itself honestly:

**K29 — the loop dropped every guardrail.** ``prompts.py`` holds the careful
prompt: the knowledge base is authoritative, don't invent specifics, be
concise. ``create_session`` persists it as message #1. But the loop built its
own three-line prompt instead, so with the flag on none of that applied.
Worse, the persisted row said "you currently have NO live access to SciTrek's
database" — false, once the model has tools — and ``GET /sessions/{id}``
replayed it, so the session history misdescribed what the model was told and
``system_prompt_hash`` keyed Phase 35 eval grouping to a prompt that never ran.

**K30 — the daily token budget could not see agent turns.**
``enforce_daily_token_budget`` sums ``prompt_tokens``/``completion_tokens`` on
assistant rows. The agent path wrote those rows with no telemetry at all, so a
turn costing six tool calls plus a summariser pass registered as zero, and the
org-wide ceiling metered only the Q&A path.

**K23 — flag-on returned a bare 500.** ``_get_agent_llm`` raised
``NotImplementedError`` and is called before the ``StreamingResponse`` exists,
so the first thing a developer saw after flipping the flag was
``Stream failed: HTTP 500``.
"""
from __future__ import annotations

import itertools
import uuid

import pytest

from app import models
from app.copilot import prompts, router as copilot_router
from app.config import settings
from tests.fixtures.helpers import auth_headers, make_user


@pytest.fixture(autouse=True)
def _enable_copilot(monkeypatch):
    monkeypatch.setattr(settings, "copilot_enabled", True)
    monkeypatch.setattr(settings, "copilot_primary_model", "primary/test:free")
    monkeypatch.setattr(settings, "copilot_fallback_model", "fallback/test:free")
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")


# ---------------------------------------------------------------------------
# K29 — the two prompt variants
# ---------------------------------------------------------------------------


class TestPromptVariants:
    def test_no_tools_variant_still_disclaims_live_access(self):
        p = prompts.system_prompt_for(models.UserRole.admin, agent=False)
        assert "NO live access" in p
        assert "data tools are coming in a later phase" in p

    def test_agent_variant_does_not_claim_it_lacks_the_tools_it_has(self):
        p = prompts.system_prompt_for(models.UserRole.admin, agent=True)
        assert "NO live access" not in p
        assert "coming in a later phase" not in p
        assert "live access to SciTrek's scheduling data through tools" in p

    def test_agent_variant_forbids_unsourced_specifics(self):
        # The single most load-bearing sentence in the agent prompt: a model
        # with tools that still guesses is worse than one that admits it
        # cannot see, because now the guess looks like a lookup.
        p = prompts.system_prompt_for(models.UserRole.admin, agent=True)
        assert "come back from a tool" in p

    def test_agent_variant_says_a_confirmation_card_is_not_a_receipt(self):
        p = prompts.system_prompt_for(models.UserRole.admin, agent=True)
        assert "not a receipt" in p

    @pytest.mark.parametrize(
        "role", [models.UserRole.admin, models.UserRole.organizer]
    )
    def test_shared_rules_are_identical_across_variants(self, role):
        """Rules 3-7 are assembled from one constant, not written twice.

        They drifted apart the moment someone edited only one copy, and the
        drift would be invisible — both prompts still read fine on their own.
        """
        qa = prompts.system_prompt_for(role, agent=False)
        agent = prompts.system_prompt_for(role, agent=True)
        for rule in (
            "3. You may answer general questions",
            "5. Be concise.",
            "6. The <retrieved_context> block",
            '7. If the retrieved excerpts don\'t cover the question',
        ):
            assert rule in qa
            assert rule in agent

    def test_role_tails_survive_the_split(self):
        admin = prompts.system_prompt_for(models.UserRole.admin, agent=True)
        organizer = prompts.system_prompt_for(
            models.UserRole.organizer, agent=True
        )
        assert "There is no quarterly CSV import" in admin
        assert "cannot see other organizers' data" in organizer

    def test_variants_hash_differently(self):
        """Otherwise Phase 35 would pool agent and Q&A runs into one bucket."""
        qa, qa_hash = prompts.render_with_profile(
            models.UserRole.admin, agent=False
        )
        ag, ag_hash = prompts.render_with_profile(
            models.UserRole.admin, agent=True
        )
        assert qa != ag
        assert qa_hash != ag_hash


# ---------------------------------------------------------------------------
# K29 — the session row describes the prompt that actually ran
# ---------------------------------------------------------------------------


_seq = itertools.count()


def _admin(db_session):
    return make_user(
        db_session,
        email=f"agent_admin_{next(_seq)}@example.com",
        role=models.UserRole.admin,
    )


class TestSessionRecordsTheRealPrompt:
    def test_agent_flag_on_persists_the_agent_prompt(
        self, client, db_session, monkeypatch
    ):
        monkeypatch.setattr(
            copilot_router.settings, "copilot_agent_loop_enabled", True
        )
        admin = _admin(db_session)
        resp = client.post("/api/v1/copilot/sessions", headers=auth_headers(client, admin))
        assert resp.status_code == 201
        sid = resp.json()["id"]

        sysmsg = (
            db_session.query(models.CopilotMessage)
            .filter(
                models.CopilotMessage.session_id == uuid.UUID(sid),
                models.CopilotMessage.role == models.CopilotMessageRole.system,
            )
            .one()
        )
        # The row the user's own /sessions/{id} replay is built from.
        assert "NO live access" not in sysmsg.content
        assert "through tools" in sysmsg.content

    def test_agent_flag_off_is_unchanged(self, client, db_session, monkeypatch):
        monkeypatch.setattr(
            copilot_router.settings, "copilot_agent_loop_enabled", False
        )
        admin = _admin(db_session)
        sid = client.post(
            "/api/v1/copilot/sessions", headers=auth_headers(client, admin)
        ).json()["id"]
        sysmsg = (
            db_session.query(models.CopilotMessage)
            .filter(
                models.CopilotMessage.session_id == uuid.UUID(sid),
                models.CopilotMessage.role == models.CopilotMessageRole.system,
            )
            .one()
        )
        assert "NO live access" in sysmsg.content

    def test_hash_on_the_row_matches_the_persisted_text(
        self, client, db_session, monkeypatch
    ):
        monkeypatch.setattr(
            copilot_router.settings, "copilot_agent_loop_enabled", True
        )
        admin = _admin(db_session)
        sid = client.post(
            "/api/v1/copilot/sessions", headers=auth_headers(client, admin)
        ).json()["id"]
        sess = db_session.get(models.CopilotSession, uuid.UUID(sid))
        sysmsg = (
            db_session.query(models.CopilotMessage)
            .filter(
                models.CopilotMessage.session_id == sess.id,
                models.CopilotMessage.role == models.CopilotMessageRole.system,
            )
            .one()
        )
        assert sess.system_prompt_hash == prompts.hash_prompt(sysmsg.content)


# ---------------------------------------------------------------------------
# K29 — the loop is handed that prompt, not one of its own
# ---------------------------------------------------------------------------


class _ScriptedLLM:
    """Records what it was asked, answers once, and reports usage."""

    def __init__(self, usage=None):
        self.calls = []
        self.usage = usage if usage is not None else {}

    def chat(self, *, messages, tools=None):
        self.calls.append({"messages": messages, "tools": tools})
        return {"final_answer": "done"}


def _drain(resp) -> str:
    return b"".join(resp.iter_bytes()).decode()


class TestLoopReceivesThePersistedPrompt:
    def _setup(self, client, db_session, monkeypatch, usage=None):
        monkeypatch.setattr(
            copilot_router.settings, "copilot_agent_loop_enabled", True
        )
        monkeypatch.setattr(
            copilot_router, "_run_retrieval", lambda db, q: ([], 0, 0)
        )
        llm = _ScriptedLLM(usage=usage)
        monkeypatch.setattr(copilot_router, "_get_agent_llm", lambda: llm)
        admin = _admin(db_session)
        sid = client.post(
            "/api/v1/copilot/sessions", headers=auth_headers(client, admin)
        ).json()["id"]
        return admin, sid, llm

    def test_system_message_is_the_session_row_not_an_improvised_one(
        self, client, db_session, monkeypatch
    ):
        admin, sid, llm = self._setup(client, db_session, monkeypatch)
        with client.stream(
            "POST",
            f"/api/v1/copilot/sessions/{sid}/messages",
            headers=auth_headers(client, admin),
            json={"content": "how many volunteers are booked this week?"},
        ) as resp:
            _drain(resp)

        assert llm.calls, "the loop never reached the model"
        system = llm.calls[0]["messages"][0]
        assert system["role"] == "system"
        # The guardrails the improvised prompt threw away.
        assert "<retrieved_context> block" in system["content"]
        assert "Be concise." in system["content"]
        # And not the improvised text itself.
        assert "You are a copilot for a UCSB SciTrek scheduler." not in (
            system["content"]
        )

    def test_prior_turns_are_replayed_and_the_new_one_is_not_duplicated(
        self, client, db_session, monkeypatch
    ):
        admin, sid, llm = self._setup(client, db_session, monkeypatch)
        for text in ("first question", "second question"):
            with client.stream(
                "POST",
                f"/api/v1/copilot/sessions/{sid}/messages",
                headers=auth_headers(client, admin),
                json={"content": text},
            ) as resp:
                _drain(resp)

        messages = llm.calls[-1]["messages"]
        contents = [m.get("content") for m in messages]
        assert contents.count("second question") == 1
        assert "first question" in contents


# ---------------------------------------------------------------------------
# K30 — the assistant row carries the turn's cost
# ---------------------------------------------------------------------------


class TestAgentTurnsAreMetered:
    def test_usage_from_the_adapter_lands_on_the_assistant_row(
        self, client, db_session, monkeypatch
    ):
        usage = {
            "prompt_tokens": 1234,
            "completion_tokens": 56,
            "latency_ms": 789,
            "model_id": "some/model:free",
            "calls": 3,
        }
        monkeypatch.setattr(
            copilot_router.settings, "copilot_agent_loop_enabled", True
        )
        monkeypatch.setattr(
            copilot_router, "_run_retrieval", lambda db, q: ([], 0, 0)
        )
        monkeypatch.setattr(
            copilot_router, "_get_agent_llm", lambda: _ScriptedLLM(usage=usage)
        )
        admin = _admin(db_session)
        sid = client.post(
            "/api/v1/copilot/sessions", headers=auth_headers(client, admin)
        ).json()["id"]
        with client.stream(
            "POST",
            f"/api/v1/copilot/sessions/{sid}/messages",
            headers=auth_headers(client, admin),
            json={"content": "hello"},
        ) as resp:
            _drain(resp)

        row = (
            db_session.query(models.CopilotMessage)
            .filter(
                models.CopilotMessage.session_id == uuid.UUID(sid),
                models.CopilotMessage.role
                == models.CopilotMessageRole.assistant,
            )
            .one()
        )
        assert row.prompt_tokens == 1234
        assert row.completion_tokens == 56
        assert row.latency_ms == 789
        assert row.model_id == "some/model:free"
        assert row.prompt_hash is not None

    def test_a_metered_turn_counts_against_the_daily_budget(
        self, client, db_session, monkeypatch
    ):
        """The whole point of recording it: the ceiling has to move."""
        from app.copilot import guardrails

        monkeypatch.setattr(
            guardrails.settings, "copilot_daily_token_budget", 1000
        )
        monkeypatch.setattr(
            copilot_router.settings, "copilot_agent_loop_enabled", True
        )
        monkeypatch.setattr(
            copilot_router, "_run_retrieval", lambda db, q: ([], 0, 0)
        )
        monkeypatch.setattr(
            copilot_router,
            "_get_agent_llm",
            lambda: _ScriptedLLM(
                usage={"prompt_tokens": 900, "completion_tokens": 200}
            ),
        )
        admin = _admin(db_session)
        sid = client.post(
            "/api/v1/copilot/sessions", headers=auth_headers(client, admin)
        ).json()["id"]
        with client.stream(
            "POST",
            f"/api/v1/copilot/sessions/{sid}/messages",
            headers=auth_headers(client, admin),
            json={"content": "hello"},
        ) as resp:
            _drain(resp)

        # 1100 > 1000: the next message must be refused. Before K30 this row
        # recorded zero tokens and the budget never moved, so a runaway agent
        # could spend the free-tier key all day without tripping the ceiling.
        with pytest.raises(Exception):
            guardrails.enforce_daily_token_budget(db_session)

    def test_a_stub_without_usage_does_not_crash_the_turn(
        self, client, db_session, monkeypatch
    ):
        monkeypatch.setattr(
            copilot_router.settings, "copilot_agent_loop_enabled", True
        )
        monkeypatch.setattr(
            copilot_router, "_run_retrieval", lambda db, q: ([], 0, 0)
        )

        class _NoUsage:
            def chat(self, *, messages, tools=None):
                return {"final_answer": "fine"}

        monkeypatch.setattr(copilot_router, "_get_agent_llm", lambda: _NoUsage())
        admin = _admin(db_session)
        sid = client.post(
            "/api/v1/copilot/sessions", headers=auth_headers(client, admin)
        ).json()["id"]
        with client.stream(
            "POST",
            f"/api/v1/copilot/sessions/{sid}/messages",
            headers=auth_headers(client, admin),
            json={"content": "hello"},
        ) as resp:
            body = _drain(resp)
        assert "final_answer" in body

        row = (
            db_session.query(models.CopilotMessage)
            .filter(
                models.CopilotMessage.session_id == uuid.UUID(sid),
                models.CopilotMessage.role
                == models.CopilotMessageRole.assistant,
            )
            .one()
        )
        assert row.prompt_tokens is None


# ---------------------------------------------------------------------------
# K23 — a missing adapter is a 503 with a reason, not a 500
# ---------------------------------------------------------------------------


class TestMissingAdapterFailsHonestly:
    def test_no_api_key_yields_503_naming_the_problem(
        self, client, db_session, monkeypatch
    ):
        from app.copilot.agent import adapter as adapter_mod

        monkeypatch.setattr(
            copilot_router.settings, "copilot_agent_loop_enabled", True
        )
        monkeypatch.setattr(
            copilot_router, "_run_retrieval", lambda db, q: ([], 0, 0)
        )
        monkeypatch.setattr(adapter_mod.settings, "openrouter_api_key", "")
        admin = _admin(db_session)
        sid = client.post(
            "/api/v1/copilot/sessions", headers=auth_headers(client, admin)
        ).json()["id"]

        resp = client.post(
            f"/api/v1/copilot/sessions/{sid}/messages",
            headers=auth_headers(client, admin),
            json={"content": "hello"},
        )
        assert resp.status_code == 503
        detail = resp.json()["detail"]
        assert "OPENROUTER_API_KEY" in detail

    def test_with_a_key_the_adapter_builds(self, monkeypatch):
        from app.copilot.agent import adapter as adapter_mod

        monkeypatch.setattr(
            adapter_mod.settings, "openrouter_api_key", "sk-or-test"
        )
        a = adapter_mod.ToolCallingAdapter()
        assert a.usage["prompt_tokens"] == 0


class TestAgentOnlyRules:
    """Rules 8-9: what the first week of real tool use taught us.

    Both are agent-only. The no-tools prompt is compared byte-for-byte
    against a checked-in fixture, so anything added for the agent has to
    stay out of the shared block or that baseline test fails.
    """

    def test_the_agent_is_told_times_are_pacific(self):
        from app.copilot import prompts
        from app import models

        agent = prompts.system_prompt_for(models.UserRole.admin, agent=True)
        assert "Pacific" in agent
        # It is the tool's job to convert, and a model that does it too
        # subtracts the offset twice.
        assert "never convert to UTC yourself" in agent

    def test_the_agent_is_told_not_to_think_out_loud(self):
        from app.copilot import prompts
        from app import models

        agent = prompts.system_prompt_for(models.UserRole.admin, agent=True)
        assert "Do not narrate your planning" in agent

    def test_the_no_tools_prompt_is_untouched_by_them(self):
        from app.copilot import prompts
        from app import models

        plain = prompts.system_prompt_for(models.UserRole.admin, agent=False)
        assert "Pacific" not in plain
        assert "Do not narrate your planning" not in plain
