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


__all__ = ["_token_count"]
