# Role-Conditioned System Prompts

## Summary

The Phase 30 copilot conditions its behavior on the caller's role
(`admin` or `organizer`) by selecting from a small fixed set of system
prompts at session creation. The selected prompt is hashed (SHA-256)
and the hash is stored on the session row alongside a human-readable
version string, enabling Phase 35 to group sessions by exact
prompt configuration when computing comparative metrics. The prompt
explicitly disclaims live data access; tool integration is deferred to
Phase 33.

## Prompt selection

`backend/app/copilot/prompts.py` exposes `system_prompt_for(role)`,
which returns:

- For `UserRole.admin`: a base prompt followed by an admin-specific
  tail describing administrative scope.
- For `UserRole.organizer`: the same base prompt followed by an
  organizer-specific tail emphasizing per-event scope.
- For any other role: a `ValueError`. Volunteer-role users are blocked
  upstream by the router with HTTP 403 and never reach this function.

## Versioning and hashing

The base + tail pair for the milestone is fixed at
`SYSTEM_PROMPT_VERSION = "v0.1.0"`. Any text edit requires a version
bump. The mechanism is intentional and documented:

1. Edit prompt text.
2. Increment the version constant.
3. New sessions record the new version + hash on `copilot_sessions`.
4. Existing sessions retain their original version + hash; their
   conversational continuity is unchanged because the prompt hash is a
   property of the session, not of the row being inserted.

The hash is the canonical fingerprint; the version is the
human-readable label. Both are recorded so that researchers reading
the database at evaluation time can identify the exact prompt without
diffing strings.

## Hard rules embedded in the prompt

The base prompt instructs the model to:

1. Acknowledge it has no live access to the SciTrek database.
2. Refuse requests for live data and recommend the relevant admin
   dashboard page.
3. Answer general questions about the application, its features, and
   its workflows.
4. Refuse to claim capabilities it does not have; respond with "I
   don't know" when uncertain.
5. Be concise.

These rules are evaluative claims that Phase 35 will measure: how
often does the model honor each rule under typical and adversarial
inputs?

## Limitations of prompt-only role enforcement

The system prompt is not a security boundary. An adversarial user may
attempt to elicit information outside the intended role through prompt
injection or social engineering. Phase 30 bounds this risk by
construction: the model has no tool access, so even successful
injection cannot exfiltrate data. Phase 33 introduces tool-boundary
enforcement — Python-level allow-listing of fields per role — which
constitutes the project's primary defense in depth and is documented
as paper contribution #1.

## Relationship to Phase 35

Phase 35 will sample `copilot_sessions` grouped by
(`model_id`, `system_prompt_version`) and report aggregate metrics
per cell. The two-dimensional grouping requires that both columns be
recorded at write time. Both are.

## References

- Bai, Y. et al. "Constitutional AI: Harmlessness from AI Feedback."
  arXiv:2212.08073 (2022). https://arxiv.org/abs/2212.08073
  (accessed 2026-05-08).
- OWASP. "Top 10 for Large Language Model Applications," LLM01
  (Prompt Injection). https://owasp.org/www-project-top-10-for-large-language-model-applications/
  (accessed 2026-05-08).
- Greshake, K. et al. "Not what you've signed up for: Compromising
  Real-World LLM-Integrated Applications with Indirect Prompt
  Injection." arXiv:2302.12173 (2023). https://arxiv.org/abs/2302.12173
  (accessed 2026-05-08).
