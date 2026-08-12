"""BASE-SEC-39: volunteer addresses must not reach the application log.

Every magic-link build and every broadcast delivery used to log the recipient's
full address at INFO, so the log slowly became a roster of which student signed
up for which module — PII in a stream that is shipped off-host and read by
people with no reason to see it. The log still needs to be usable for matching
one delivery to one complaint, so the address is masked rather than dropped.
"""
import logging

from app.observability import mask_email


def test_masking_keeps_the_domain_and_hides_the_person():
    assert mask_email("anderson@ucsb.edu") == "a******n@ucsb.edu"


def test_short_locals_do_not_leak_themselves():
    """A two-character local part has nothing left to mask if both ends stay."""
    assert mask_email("ab@ucsb.edu") == "a*@ucsb.edu"
    assert mask_email("a@ucsb.edu") == "a*@ucsb.edu"


def test_anything_unparseable_is_dropped_rather_than_guessed_at():
    assert mask_email("not-an-address") == "(redacted)"
    assert mask_email("") == "(redacted)"
    assert mask_email(None) == "(redacted)"
    assert mask_email("@ucsb.edu") == "(redacted)"


def test_building_a_magic_link_does_not_log_the_address(caplog, db_session):
    """The regression guard: this is the line that logged it on every signup."""
    from app import models
    from app.emails import build_magic_link_email

    event = models.Event(title="Redaction check")
    email = "logleak@example.com"

    with caplog.at_level(logging.DEBUG, logger="app.emails"):
        build_magic_link_email(email, "tok" * 12, event, "http://localhost:8000")

    joined = "\n".join(r.getMessage() for r in caplog.records)
    assert joined, "expected the build to log something to match deliveries by"
    assert email not in joined
    assert "l*****k@example.com" in joined
