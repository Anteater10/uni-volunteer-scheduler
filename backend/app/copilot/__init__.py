"""Phase 30 (v1.4): AI Onboarding Copilot.

Subpackage layout:
- ``prompts``: role-aware system prompts + version constants.
- ``llm``: thin wrapper around OpenRouter via the ``openai`` SDK; primary
  and fallback model selection; streaming + non-streaming helpers.
- ``schemas``: Pydantic request/response shapes for the public router.
- ``router``: FastAPI router mounted at ``/api/v1/copilot``.

The flag ``settings.copilot_enabled`` gates the whole router; turning it
off returns 404 to keep the surface invisible. Volunteer accounts are
rejected with 403 — Phase 30 is admin + organizer only.
"""
