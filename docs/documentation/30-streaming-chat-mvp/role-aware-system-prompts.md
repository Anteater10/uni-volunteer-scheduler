# Role-Conditioned System Prompts

> _Stub — to be filled in alongside the system-prompt module._

## Summary

The Phase 30 copilot conditions its behavior on the caller's role
(`admin` or `organizer`) by selecting from a small fixed set of system
prompts at session creation. The chosen prompt is hashed (SHA-256) and
the hash is stored on the session row, enabling Phase 35 to group
sessions by prompt version when computing comparative metrics. The
prompt explicitly disclaims live data access until Phase 33 introduces
the tool layer; this is a deliberate scope boundary, not an oversight.

## Limitations of prompt-only role enforcement

The system prompt is not a security boundary; an adversarial user may
attempt to elicit information outside their role through prompt
injection or social engineering. Phase 30 has no live PII access, so
this risk is bounded; Phase 33 introduces tool-boundary enforcement to
mitigate the general case.

## References

- To be added at fill-in.
