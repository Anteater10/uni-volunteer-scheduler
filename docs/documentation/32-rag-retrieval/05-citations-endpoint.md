# GET /api/v1/copilot/citations/{chunk_id}

Phase 32 Plan 05 — click-through lookup for a single corpus chunk.
Consumed by the citation-chip popover shipped in Plan 32-06.

## Endpoint contract

| Property | Value |
|---|---|
| Method | `GET` |
| Path | `/api/v1/copilot/citations/{chunk_id}` |
| Auth | Bearer token, role ∈ {admin, organizer} |
| Feature flag | `settings.copilot_enabled` must be true (else 404) |
| Path param | `chunk_id: UUID` (Starlette UUID converter) |
| Response | `CitationDetail` (200) |

### Path parameters

| Name | Type | Notes |
|---|---|---|
| `chunk_id` | `UUID` | Returned to the client on the `event: meta` SSE payload as `Citation.chunk_id`. Non-UUID values are 422'd at parse time (RESEARCH §V5 / §Pattern 6 — see Security analysis). |

### Response — `200 OK`

```json
{
  "source_path": "docs/handbook.md",
  "char_start": 0,
  "char_end": 42,
  "content": "Volunteers help SciTrek run quarterly events.",
  "document_url": ""
}
```

Schema (`backend/app/copilot/schemas.py::CitationDetail`):

| Field | Type | Notes |
|---|---|---|
| `source_path` | `str` | Repo-relative path of the document the chunk came from, as recorded by the Phase 31 corpus walker. |
| `char_start` | `int` | Character offset of the chunk within the document, inclusive. |
| `char_end` | `int` | Character offset of the chunk's end, exclusive. |
| `content` | `str` | The full text of the chunk. Up to `settings.corpus_chunk_size` characters (currently 1024). |
| `document_url` | `str` | External URL to the source file. `""` when `settings.corpus_source_origin_url` is unset — see Security analysis. |

### Response — `404 Not Found`

```json
{
  "error": "http_404",
  "code": "http_404",
  "detail": "Citation not found"
}
```

Emitted when `chunk_id` is a well-formed UUID that doesn't match any
row. The `error` and `code` wrappers come from the global
`http_exception_handler` (AUDIT-03, `backend/app/main.py`); the
`detail` field is what this handler raises.

### Response — `403 Forbidden`

Returned when the authenticated user's role is not `admin` or
`organizer`. Body shape is the standard AUDIT-03 envelope. Same
guard applied to every Phase 30/32 copilot endpoint.

### Response — `422 Unprocessable Entity`

Returned by FastAPI/Starlette when `chunk_id` is not a valid UUID
(e.g. `not-a-uuid`, URL-encoded path traversal attempts, hex too
short). No handler code runs in this case.

### Response — `401 Unauthorized`

Returned when no Bearer token is supplied or the token is invalid.
Standard Phase 0 auth middleware behaviour.

## Computed `document_url`

```text
origin = settings.corpus_source_origin_url.rstrip("/")
document_url = ""
if origin:
    document_url = f"{origin}/{row.source_path.lstrip('/')}"
```

| Setting value | Result |
|---|---|
| `""` (default) | `document_url == ""` |
| `"https://github.com/Anteater10/uni-volunteer-scheduler/blob/main"` | `https://.../blob/main/<source_path>` |
| `"https://.../main/"` (trailing slash) | Same as above — `rstrip('/')` normalises. |
| `source_path` stored as `/docs/x.md` (leading slash) | Same as `docs/x.md` — `lstrip('/')` normalises. |

The frontend treats an empty string as "render the chip without a
link." There is no fallback URL.

## SQL

The handler runs a single SELECT:

```sql
SELECT cc.char_start, cc.char_end, cc.content, cd.source_path
FROM corpus_chunks cc
JOIN corpus_documents cd ON cd.id = cc.document_id
WHERE cc.id = :id
```

Parameterised via SQLAlchemy `text()` (Phase 31 ORM-frozen convention).
One round-trip, indexed on `corpus_chunks.id` (primary key).

## Security analysis

### T-32-05-01 — Tampering (path traversal) on `chunk_id`

**Disposition:** mitigate (RESEARCH §Pattern 6).

`chunk_id: UUID` forces the Starlette UUID converter to parse the path
segment. Non-UUID inputs are rejected with `422 Unprocessable Entity`
before any handler code runs and before any SQL is constructed.
Parameterised SQL provides a second layer of defense inside the
handler, but the parse-layer check is the load-bearing control —
there is no code path from a malformed `chunk_id` to a database query.

### T-32-05-02 — Information disclosure (corpus content)

**Disposition:** accept.

The corpus is restricted to non-PII repo content by the Phase 31
walker (`backend/app/corpus/walker.py`). All callers of this endpoint
are admin or organizer roles. Returning the full chunk content to an
authenticated insider is the explicit purpose of the endpoint.

### T-32-05-03 — Information disclosure via `document_url`

**Disposition:** mitigate.

A naive implementation would always emit a URL containing the
`source_path`, which leaks the internal repo layout to the browser's
address bar history, the user's clipboard, and any analytics that
scrape outbound link clicks. The mitigation is the empty-default
pattern: `settings.corpus_source_origin_url` defaults to `""`, and the
handler emits `document_url=""` in that case. Operators opt in to
external linking by setting the env var to the desired repo URL prefix
(e.g. `https://github.com/Anteater10/uni-volunteer-scheduler/blob/main`).
The absence of configuration is the safe state.

### Defense against feature-flag bypass

The handler calls `_require_flag_on()` before any other work, so when
`settings.copilot_enabled` is false the route 404s. This matches the
behaviour of every other copilot endpoint — the entire surface
disappears when the flag is off rather than 403'ing, denying an
attacker information about which routes exist.

## Tests

`backend/tests/test_copilot_citations_endpoint.py` (6 tests):

| Test | Asserts |
|---|---|
| `test_get_citation_success` | 200 + full body shape with default empty origin. |
| `test_get_citation_404_for_unknown_id` | 404 with `detail == "Citation not found"`. |
| `test_get_citation_403_unauthorized` | Participant role → 403. |
| `test_get_citation_422_on_invalid_uuid` | `/citations/not-a-uuid` → 422 from Starlette. |
| `test_document_url_empty_when_origin_unset` | Default origin → `document_url == ""`. |
| `test_document_url_computed_when_origin_set` | Trailing-slash origin + leading-slash source_path → single-slash join. |

`app.copilot.router.py` line coverage 99 %; `app.copilot.schemas.py`
line coverage 96 % (Plan 32-05 additions fully exercised).

## References

- `backend/app/copilot/router.py::get_citation`
- `backend/app/copilot/schemas.py::CitationDetail`
- `backend/app/config.py::Settings.corpus_source_origin_url`
- `.planning/phases/32-rag-retrieval/32-RESEARCH.md` §V5 / §Pattern 6
- Paired learning lecture: `docs/learning/32-rag-retrieval/05-citations-endpoint.md`
