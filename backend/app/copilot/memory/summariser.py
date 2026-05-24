"""Phase 34: within-session history compression.

The agent loop calls :func:`compress_if_needed` before every
``llm.chat()``. If the token count of ``messages`` exceeds 70% of the
active model's context window, the older turns get rolled up into a
single synthetic system message (``"## Conversation so far\\n<synopsis>"``)
and the last two user/assistant pairs are kept verbatim.

Tokenisation notes
------------------
We use ``tiktoken`` for token counting. OpenRouter routes most of its
free models (Mistral, Llama-3, Qwen, etc.) which do not ship an official
tokenizer registered with ``tiktoken.encoding_for_model``. We therefore
fall back to the ``cl100k_base`` encoding — the same encoding used by
GPT-3.5 / GPT-4 family models, which is the de-facto standard for any
OpenAI-compatible chat completions surface. The count is an
approximation, not an exact billing figure, which is fine: we only need
it to decide whether to compress, not to bill the user.
"""
from __future__ import annotations

import json
from typing import Any

import tiktoken


CONTEXT_WINDOW_DEFAULT = 8192
THRESHOLD_RATIO = 0.7
WORKING_SET_PAIRS = 2


def _encoding_for(model: str):
    try:
        return tiktoken.encoding_for_model(model)
    except Exception:
        return tiktoken.get_encoding("cl100k_base")


def _token_count(messages: list[dict[str, Any]], *, model: str) -> int:
    enc = _encoding_for(model)
    total = 0
    for m in messages:
        if not isinstance(m, dict):
            continue
        content = m.get("content")
        if isinstance(content, str):
            total += len(enc.encode(content))
        for tc in m.get("tool_calls", []) or []:
            fn = tc.get("function", {}) if isinstance(tc, dict) else {}
            total += len(enc.encode(fn.get("name", "")))
            args = fn.get("arguments", "")
            if isinstance(args, (dict, list)):
                args = json.dumps(args)
            total += len(enc.encode(args or ""))
        if m.get("name"):
            total += len(enc.encode(m["name"]))
    return total


def _format_for_summary(msgs: list[dict[str, Any]]) -> str:
    """Render older turns as a compact transcript for the summariser LLM."""
    lines: list[str] = []
    for m in msgs:
        role = m.get("role", "?")
        if role == "tool":
            lines.append(f"[tool:{m.get('name', '')}] (result omitted)")
            continue
        content = m.get("content") or ""
        tool_calls = m.get("tool_calls") or []
        if tool_calls:
            names = [
                (tc.get("function", {}) if isinstance(tc, dict) else {}).get(
                    "name", "?"
                )
                for tc in tool_calls
            ]
            lines.append(f"{role}: <called {', '.join(names)}>")
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _build_compression_prompt(
    to_compress: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build the chat messages sent to the summariser LLM.

    Single-user-turn prompt is enough — the older transcript is already
    role-prefixed inside ``_format_for_summary``, so we don't need to
    replay the original system prompt here.
    """
    transcript = _format_for_summary(to_compress)
    prompt = (
        "Summarise these prior turns into a short synopsis "
        "(<=200 words). Preserve facts the user might reference later. "
        "Note any tool calls made (one-line summaries, not full "
        "payloads).\n\n"
        f"{transcript}"
    )
    return [{"role": "user", "content": prompt}]


def _summarise(older: list[dict[str, Any]], *, llm) -> str:
    messages = _build_compression_prompt(older)
    try:
        resp = llm.chat(messages=messages, tools=None)
    except Exception:
        return "[summariser failed; older turns dropped]"
    if isinstance(resp, dict):
        return resp.get("final_answer") or resp.get("content") or ""
    return str(resp)


def compress_if_needed(
    messages: list[dict[str, Any]],
    *,
    llm,
    model: str,
    context_window: int = CONTEXT_WINDOW_DEFAULT,
    threshold: float = THRESHOLD_RATIO,
    working_set_pairs: int = WORKING_SET_PAIRS,
) -> list[dict[str, Any]]:
    """Compress older turns into a synopsis when token usage > threshold.

    Returns ``messages`` unchanged when usage is under
    ``threshold * context_window``. Otherwise returns
    ``[*leading_system_msgs, synthetic_synopsis, *working_set]`` where
    the working set is the last ``working_set_pairs`` user/assistant
    pairs (plus any tool entries that sit inside that window).
    """
    if not messages:
        return messages
    used = _token_count(messages, model=model)
    if used < threshold * context_window:
        return messages

    system_msgs = [m for m in messages if m.get("role") == "system"]
    body = [m for m in messages if m.get("role") != "system"]

    # Walk backwards through the body, counting user turns. The cut
    # index lands on the user message that starts the working set.
    pairs_seen = 0
    cut_index = 0
    for i in range(len(body) - 1, -1, -1):
        if body[i].get("role") == "user":
            pairs_seen += 1
            if pairs_seen >= working_set_pairs:
                cut_index = i
                break
    older = body[:cut_index]
    working_set = body[cut_index:]

    if not older:
        return messages

    synopsis = _summarise(older, llm=llm)
    synthetic = {
        "role": "system",
        "content": f"## Conversation so far\n{synopsis}",
    }
    return system_msgs + [synthetic] + working_set


__all__ = [
    "_token_count",
    "_build_compression_prompt",
    "compress_if_needed",
    "CONTEXT_WINDOW_DEFAULT",
    "THRESHOLD_RATIO",
    "WORKING_SET_PAIRS",
]
