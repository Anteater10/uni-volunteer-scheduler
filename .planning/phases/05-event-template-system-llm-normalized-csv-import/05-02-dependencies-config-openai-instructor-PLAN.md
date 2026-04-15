---
phase: 05
plan: 02
name: "Dependencies & Config — openai, instructor, env vars"
wave: 1
depends_on: []
files_modified:
  - backend/requirements.txt
  - backend/app/config.py
  - .env.example
  - backend/data/corpus/.gitkeep
autonomous: true
requirements:
  - "Stage 1 LLM extraction (instructor + Pydantic structured output, gpt-4o-mini)"
  - "raw-to-normalized corpus logging"
---

# Plan 05-02: Dependencies & Config — openai, instructor, env vars

<objective>
Add `openai` and `instructor` Python packages to backend dependencies. Extend the
settings model with `OPENAI_API_KEY`, `OPENAI_MODEL` (default `gpt-4o-mini`), and
`IMPORT_COST_CEILING` (default 5.0). Create the corpus logging directory with .gitignore.
Update `.env.example` with new vars.
</objective>

<must_haves>
- `openai` and `instructor` packages in `backend/requirements.txt`
- `config.py` settings: `openai_api_key: str = ""`, `openai_model: str = "gpt-4o-mini"`, `import_cost_ceiling: float = 5.0`
- `.env.example` includes `OPENAI_API_KEY=`, `OPENAI_MODEL=gpt-4o-mini`, `IMPORT_COST_CEILING=5.0`
- `backend/data/corpus/` directory with `.gitkeep` and a `.gitignore` that ignores `*.jsonl`
</must_haves>

<tasks>

<task id="05-02-01" parallel="true">
<read_first>
- backend/requirements.txt
</read_first>
<action>
Edit `backend/requirements.txt` — append these lines (after existing deps):

```
openai>=1.30.0
instructor>=1.3.0
```
</action>
<acceptance_criteria>
- `grep "openai" backend/requirements.txt` returns a match
- `grep "instructor" backend/requirements.txt` returns a match
</acceptance_criteria>
</task>

<task id="05-02-02" parallel="true">
<read_first>
- backend/app/config.py
</read_first>
<action>
Edit `backend/app/config.py` — add to the Settings class:

```python
# --- Phase 5: LLM CSV Import ---
openai_api_key: str = ""  # TODO(secret): real key in local .env only
openai_model: str = "gpt-4o-mini"
import_cost_ceiling: float = 5.0  # refuse imports estimated > $5
```
</action>
<acceptance_criteria>
- `grep "openai_api_key" backend/app/config.py` returns a match
- `grep "openai_model" backend/app/config.py` returns a match
- `grep "import_cost_ceiling" backend/app/config.py` returns a match
- `grep "gpt-4o-mini" backend/app/config.py` returns a match
</acceptance_criteria>
</task>

<task id="05-02-03" parallel="true">
<read_first>
- .env.example
</read_first>
<action>
Edit `.env.example` — append:

```
# --- Phase 5: LLM CSV Import ---
OPENAI_API_KEY=  # TODO(secret): get from OpenAI dashboard
OPENAI_MODEL=gpt-4o-mini
IMPORT_COST_CEILING=5.0
```
</action>
<acceptance_criteria>
- `grep "OPENAI_API_KEY" .env.example` returns a match
- `grep "OPENAI_MODEL" .env.example` returns a match
- `grep "IMPORT_COST_CEILING" .env.example` returns a match
</acceptance_criteria>
</task>

<task id="05-02-04" parallel="true">
<read_first></read_first>
<action>
Create corpus logging directory:

```bash
mkdir -p backend/data/corpus
touch backend/data/corpus/.gitkeep
```

Create `backend/data/corpus/.gitignore`:
```
*.jsonl
```

This ensures the directory exists in git but corpus JSONL files (which can be large)
are not committed.
</action>
<acceptance_criteria>
- `test -d backend/data/corpus` exits 0
- `test -f backend/data/corpus/.gitkeep` exits 0
- `test -f backend/data/corpus/.gitignore` exits 0
- `grep "jsonl" backend/data/corpus/.gitignore` returns a match
</acceptance_criteria>
</task>

</tasks>

<verification>
- `pip install -r backend/requirements.txt` installs without errors
- `python -c "import openai; import instructor; print('OK')"` exits 0
- `python -c "from app.config import settings; assert settings.openai_model == 'gpt-4o-mini'"` exits 0
- `backend/data/corpus/.gitignore` exists and ignores `*.jsonl`
</verification>

<threat_model>
- **API key exposure:** `OPENAI_API_KEY` defaults to empty string. `.env.example` has no real key. The `.env` file (with real key) is already in `.gitignore`. Config reads from env var at runtime — no key in source.
- **Cost control:** `import_cost_ceiling` defaults to $5. Plan 05 enforces this ceiling before calling the LLM. No risk at config level.
</threat_model>
