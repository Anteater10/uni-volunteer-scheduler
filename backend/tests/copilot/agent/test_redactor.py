import copy

from app.copilot.agent.boundary.redactor import RedactionEvent, scrub


def test_email_redacted_in_string():
    data = {"note": "contact alice@example.com please"}
    out, events = scrub(data, declared=True)
    assert "alice@example.com" not in out["note"]
    assert "[REDACTED:email]" in out["note"]
    assert len(events) == 1
    assert events[0].kind == "email"
    assert events[0].severity == "LOW"


def test_phone_redacted_various_formats():
    cases = [
        "call (805) 555-1234 now",
        "call 805-555-1234 now",
        "call +1 805 555 1234 now",
        "call 8055551234 now",
    ]
    for s in cases:
        out, events = scrub({"n": s}, declared=True)
        assert "[REDACTED:phone]" in out["n"], f"failed for input: {s!r}"
        assert any(e.kind == "phone" for e in events), f"no phone event for {s!r}"


def test_ssn_redacted():
    out, events = scrub({"n": "SSN: 123-45-6789"}, declared=True)
    assert "123-45-6789" not in out["n"]
    assert "[REDACTED:ssn]" in out["n"]
    assert any(e.kind == "ssn" for e in events)


def test_ucsb_nid_redacted():
    out, events = scrub({"n": "NID is abc1234567 here"}, declared=True)
    assert "abc1234567" not in out["n"]
    assert "[REDACTED:ucsb_nid]" in out["n"]
    assert any(e.kind == "ucsb_nid" for e in events)


def test_high_severity_when_undeclared():
    out, events = scrub({"note": "alice@example.com"}, declared=False)
    assert events
    assert all(e.severity == "HIGH" for e in events)


def test_nested_dict_and_list_walk():
    data = {
        "roster": [
            {"note": "ok"},
            {"note": "email me at bob@x.com"},
        ],
        "meta": {"contact": {"line": "ssn 123-45-6789"}},
    }
    out, events = scrub(data, declared=True)
    paths = {e.path for e in events}
    assert "roster.1.note" in paths
    assert "meta.contact.line" in paths
    # original_len should be the matched substring length
    for e in events:
        assert e.original_len > 0


def test_non_string_values_untouched():
    data = {"a": 1, "b": True, "c": None, "d": 3.14}
    out, events = scrub(data, declared=True)
    assert out == {"a": 1, "b": True, "c": None, "d": 3.14}
    assert events == []


def test_no_matches_returns_empty_events():
    data = {"note": "just a friendly hello", "n": 5}
    out, events = scrub(data, declared=True)
    assert out == data
    assert events == []


def test_original_not_mutated():
    data = {"roster": [{"note": "email alice@example.com"}]}
    snapshot = copy.deepcopy(data)
    out, events = scrub(data, declared=True)
    assert data == snapshot
    # and the output should differ
    assert out != data


def test_redaction_event_fields():
    out, events = scrub({"note": "alice@example.com"}, declared=True)
    assert len(events) == 1
    ev = events[0]
    assert isinstance(ev, RedactionEvent)
    assert ev.kind == "email"
    assert ev.path == "note"
    assert ev.original_len == len("alice@example.com")
    assert ev.severity == "LOW"
