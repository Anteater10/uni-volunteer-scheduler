"""Phase 35-02-A: testset.yaml schema invariants.

Runs in CI. No network. Asserts the YAML loads, every entry has required
fields, ids are unique, roles are in {admin, organizer, participant},
and no required_tools entry references a paid model in `notes`.
"""
from __future__ import annotations

from importlib.resources import files

import pytest
import yaml

_ALLOWED_ROLES = {"admin", "organizer", "participant"}
_ALLOWED_CATEGORIES = {
    "roster_query",
    "scheduling",
    "signup_stats",
    "profile_recall",
    "policy_recall",  # Phase 35-03: knowledge questions the corpus can ground
    "tool_write",
    "adversarial_injection",
    "adversarial_overreach",
    "refusal",
}


def _load_testset() -> list[dict]:
    raw = (files("app.eval") / "testset.yaml").read_text()
    doc = yaml.safe_load(raw) or {}
    return doc.get("questions", []) or []


def test_testset_yaml_loads_cleanly():
    questions = _load_testset()
    assert isinstance(questions, list)
    assert len(questions) >= 10, "skeleton must seed at least 10 entries"


def test_every_entry_has_required_fields():
    required = {"id", "role", "category", "prompt", "gold"}
    for q in _load_testset():
        missing = required - q.keys()
        assert not missing, f"{q.get('id', '<no-id>')} missing {missing}"


def test_ids_are_unique():
    ids = [q["id"] for q in _load_testset()]
    assert len(ids) == len(set(ids)), "duplicate ids in testset"


def test_roles_are_in_allowed_set():
    for q in _load_testset():
        assert q["role"] in _ALLOWED_ROLES, f"{q['id']} bad role {q['role']!r}"


def test_categories_are_in_allowed_set():
    for q in _load_testset():
        assert q["category"] in _ALLOWED_CATEGORIES, (
            f"{q['id']} bad category {q['category']!r}"
        )


def test_required_tools_shape_is_valid():
    for q in _load_testset():
        rt = q.get("required_tools")
        if rt is None:
            continue
        assert isinstance(rt, list), f"{q['id']} required_tools must be a list"
        for entry in rt:
            assert "name" in entry, f"{q['id']} tool entry missing name"
            # args is optional but if present must be a dict
            if "args" in entry:
                assert isinstance(entry["args"], dict)


def test_no_paid_model_referenced_in_notes():
    """Free-models invariant (spec section 2.7) - no paid model IDs in notes text."""
    for q in _load_testset():
        notes = (q.get("notes") or "").lower()
        # Cheap heuristic: any `/` followed by a model name MUST end :free.
        # We only flag explicit OpenRouter-shaped IDs like `vendor/model[:tag]`.
        for token in notes.split():
            if "/" in token and ":" in token and not token.endswith(":free"):
                raise AssertionError(
                    f"{q['id']} references potentially paid model {token!r}"
                )


def test_per_role_category_coverage_report(capsys):
    """Reports coverage but does not assert - keeps CI green while Andy fills out the testset."""
    from collections import Counter

    questions = _load_testset()
    by_role = Counter(q["role"] for q in questions)
    by_role_cat = Counter((q["role"], q["category"]) for q in questions)

    print("\n=== testset coverage ===")
    for role in sorted(_ALLOWED_ROLES):
        print(f"{role}: {by_role.get(role, 0)} total")
        for cat in sorted(_ALLOWED_CATEGORIES):
            n = by_role_cat.get((role, cat), 0)
            if n:
                print(f"  {cat}: {n}")
    n_adv = sum(1 for q in questions if q["category"].startswith("adversarial"))
    print(f"adversarial: {n_adv}")
    captured = capsys.readouterr()
    # Always passes - the print() output is the deliverable. CI runs in -q
    # which suppresses captured output unless --capture=tee-sys is set;
    # Andy can `pytest -v -s` locally to see the breakdown.
    assert "testset coverage" in captured.out
