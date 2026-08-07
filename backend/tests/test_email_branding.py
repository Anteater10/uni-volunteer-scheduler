"""K20 — every volunteer email was branded for a product that doesn't exist.

`base.html` wraps every templated email, and it said **"University Volunteer
Scheduler"** in the header and the footer. Nobody at UCSB has heard of that.
Volunteers signed up for SciTrek, from a scitrek address, off a SciTrek
flyer — an unfamiliar product name at the top of the message is what a
phishing email looks like, and it is the reason people don't click the
confirm button.

These tests pin the wrapper, since that is the single place all of it goes
wrong or right at once.
"""
import re
from pathlib import Path

import pytest

from app.email_templates import __file__ as templates_init

TEMPLATE_DIR = Path(templates_init).parent
WRAPPED_TEMPLATES = [
    "confirmation.html",
    "cancellation.html",
    "reminder.html",
    "reschedule.html",
    "waitlist_cancellation.html",
]


def _base() -> str:
    return (TEMPLATE_DIR / "base.html").read_text()


def test_the_wrapper_names_scitrek():
    body = _base()
    assert "UCSB SciTrek" in body
    assert "University Volunteer Scheduler" not in body


def test_the_wrapper_does_not_say_sci_trek_as_two_words():
    assert not re.search(r"\bSci Trek\b", _base())


def test_the_footer_explains_why_the_email_arrived():
    # The old footer was "helping you make a difference" — a slogan. For an
    # account-less product the footer is the only place that can tell a
    # volunteer why they're hearing from us at all.
    body = _base()
    footer = body.split("$content", 1)[1]
    assert "signed up to volunteer with UCSB SciTrek" in footer


def test_the_wrapper_still_has_its_substitution_point():
    # A branding edit that drops $content silently blanks every email.
    assert "$content" in _base()


@pytest.mark.parametrize("name", WRAPPED_TEMPLATES)
def test_no_unresolved_placeholders_left_in_shipped_templates(name):
    body = (TEMPLATE_DIR / name).read_text()
    assert "TODO(brand)" not in body
    assert "TODO(copy):" not in body


def test_rendered_email_carries_the_brand_end_to_end():
    from app.emails import _render_html

    html = _render_html(
        "confirmation.html",
        user_name="Ada Lovelace",
        event_title="Germs at Goleta Valley",
        slot_when="Mon 25 May, 9:00 AM",
        event_location="Goleta Valley JH",
        manage_url="https://example.com/manage",
    )
    assert "UCSB SciTrek" in html
    assert "University Volunteer Scheduler" not in html
