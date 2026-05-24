# Lecture 34-04 — Compressing chat history for long-context agents

> A teaching companion to `backend/app/copilot/memory/summariser.py`.

## The problem

Every turn of a chat-style LLM agent re-sends the entire prior
conversation: system prompt, user/assistant exchanges, tool calls,
tool results, the lot. That means:

- The token bill grows roughly quadratically with conversation
  length: turn N pays for messages 1..N-1 plus its own response.
- Eventually the conversation exceeds the model's context window
  and the request errors out (or, worse, the model silently drops
  the oldest content and starts confabulating).

You need a way to **shrink older history** without losing the facts
the user might reference later. There are three families of
techniques. We picked one for Phase 34; the others are worth knowing.

## Option A — rolling summary (what we shipped)

Keep the last N user/assistant pairs verbatim. Everything older gets
compressed into a one-paragraph synopsis at the top of the message
list, prefixed with a system note so the model knows it's a recap and
not a real user turn.

**Failure mode it prevents:** unbounded growth. As long as the
synopsis fits in a fixed budget, total tokens per turn stay bounded.

**Worked example.** A volunteer has a 20-turn session that's drifted
into 12k tokens. The model is gpt-4o-mini (8k window). Without
compression, turn 21 errors before the model can respond. With our
summariser: turn 21 builds messages, sees `used=12k > 0.7 * 8k =
5.6k`, calls the summariser LLM with everything except the last 2
pairs, gets back `"User confirmed availability MW 2-4pm, asked about
SciTrek-East site; assistant called list_modules twice, found 3
matching modules…"`, and sends `[system, synopsis, last-4-msgs,
new-user-msg]` to the real LLM — total ~1.5k tokens.

**Drift risk.** Because we recompute the synopsis from the full raw
history every time (not from the previous synopsis + new turns), we
avoid the "game of telephone" failure where each re-compression
loses a little more detail.

## Option B — map-reduce summarisation

Used by tools like LangChain's MapReduceDocumentsChain. Split the
history into chunks, summarise each chunk in parallel, then summarise
the summaries. Mostly used for offline document QA, not chat agents.

**Failure mode it prevents:** very long *single* documents that
don't fit in a single LLM call.

**Worked example.** Summarising a 200-page PDF: split into 20-page
chunks, summarise each, then run a final "summary of summaries" pass.

**Why we didn't pick it for chat history.** Chat history is already
chunked by turn, and individual turns are small. The win
(parallelism) doesn't apply, and the cost (two LLM passes) is real.

## Option C — vector store / retrieval-augmented memory

Embed every past turn into a vector DB. At inference time, retrieve
the top-K most relevant turns and inject them into the prompt.

**Failure mode it prevents:** "the user mentioned their dietary
restriction 50 turns ago and the agent forgot."

**Worked example.** Agent libraries like MemGPT and Letta. The user
says "my kid is gluten-free" on turn 3. On turn 47, the user asks
"any module options for next week?" — the retrieval system pulls
the gluten-free fact back into context.

**Why we didn't pick it for v1.** Three reasons. First, infra cost:
we'd need a pgvector table per session and an embedder call per
turn. Second, recall is fuzzy — if the model phrases the retrieval
query badly, the gluten-free fact is invisible. Third, our sessions
are short (10–30 turns typical), so a working set + synopsis covers
the vast majority of references. Phase 34-06 (profile extractor)
*does* persist long-lived facts to `copilot_user_profiles`, which is
the durable-memory layer; the summariser is just for *within-session*
compression.

## Why threshold = 0.7 and working_set_pairs = 2

These are knobs, not laws. The numbers come from two judgements:

- Leaving 30 % of the window free gives the model headroom for its
  own response plus a tool-call round-trip or two before the next
  compression check fires. Lower thresholds compress too eagerly
  (wasting LLM calls); higher thresholds risk blowing the window
  mid-tool-call when the model's own output pushes us over.
- Two pairs of verbatim history is the smallest amount that lets
  follow-up questions resolve their pronouns ("what about next
  week?" → next week relative to *what*?).

Both knobs are surfaced as keyword args, so when we eventually plumb
in real eval data we can A/B them without touching call sites.

## Why `cl100k_base` fallback

`tiktoken` ships exact encodings for OpenAI models. OpenRouter free
models (Mistral, Llama-3, Qwen) don't have a registered tiktoken
encoding, so `tiktoken.encoding_for_model("openrouter/mistral-7b")`
raises `KeyError`. We catch that and fall back to `cl100k_base` —
GPT-3.5 / GPT-4's encoding — which has become the de-facto standard
for any OpenAI-compatible chat surface. Counts are approximate, which
is fine because we only use them to decide whether to compress, not
to bill anyone.

## What to look for in the code

- `_token_count` is intentionally permissive — it iterates dicts,
  skips non-dicts, treats missing fields as empty strings. We never
  want a malformed message to crash the compression check.
- `_summarise` swallows LLM exceptions and returns a sentinel string.
  This is the right tradeoff: if the summariser LLM is down, we'd
  rather drop older context with a visible breadcrumb than fail the
  whole user request.
- The synopsis goes in *after* the leading system messages, not
  before. That ordering matters — system prompts set the agent's
  identity and tool-use policy; the synopsis is conversational
  state. Mixing them up confuses the model about whose turn it is.

## Check-in question

If a session runs 50 turns where the user never references anything
older than the last two exchanges, do we still need the synopsis?
What signal could we use to *skip* the summariser LLM call in that
case?
