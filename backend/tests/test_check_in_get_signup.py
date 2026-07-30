"""Sweep remediation: GET /signups/{signup_id} (check_in.py) had no auth and
returned the full SignupRead — including volunteer_id and the volunteer's
custom-form answers — to anyone who knew the signup_id.

Kept intentionally no-auth: it matches the sibling POST self-check-in
endpoint's trust model (signup_id is the credential; no visibility gate
either, since self-check-in also works for private-event signups, gated by
venue_code instead). The fix narrows the response to exactly what
SelfCheckInPage.jsx renders.
"""
import uuid
from datetime import date as date_type
from datetime import datetime, timedelta, timezone

from app.models import (
    CustomAnswer,
    CustomQuestion,
    Event,
    Signup,
    SignupStatus,
    Slot,
    SlotType,
    Volunteer,
)
from tests.fixtures.helpers import make_user


class TestGetSignupNarrowedResponse:
    def _make_signup_with_answer(self, db_session):
        owner = make_user(db_session)
        now = datetime.now(timezone.utc) + timedelta(days=1)
        event = Event(
            id=uuid.uuid4(),
            owner_id=owner.id,
            title="Answer Leak Event",
            start_date=now,
            end_date=now + timedelta(days=1),
            visibility="public",
        )
        db_session.add(event)
        db_session.flush()
        slot = Slot(
            id=uuid.uuid4(),
            event_id=event.id,
            start_time=now,
            end_time=now + timedelta(hours=2),
            capacity=5,
            current_count=1,
            slot_type=SlotType.PERIOD,
            date=date_type.today(),
        )
        db_session.add(slot)
        db_session.flush()
        volunteer = Volunteer(
            id=uuid.uuid4(),
            email="leak-target@example.com",
            first_name="Leak",
            last_name="Target",
        )
        db_session.add(volunteer)
        db_session.flush()
        signup = Signup(
            id=uuid.uuid4(),
            volunteer_id=volunteer.id,
            slot_id=slot.id,
            status=SignupStatus.confirmed,
        )
        db_session.add(signup)
        db_session.flush()
        question = CustomQuestion(
            id=uuid.uuid4(),
            event_id=event.id,
            prompt="Any allergies?",
            field_type="text",
        )
        db_session.add(question)
        db_session.flush()
        answer = CustomAnswer(
            id=uuid.uuid4(),
            signup_id=signup.id,
            question_id=question.id,
            value="peanut allergy -- call 555-1234",
        )
        db_session.add(answer)
        db_session.commit()
        return event, slot, signup, volunteer

    def test_response_excludes_answers_and_volunteer_id(self, client, db_session):
        event, slot, signup, volunteer = self._make_signup_with_answer(db_session)

        resp = client.get(f"/api/v1/signups/{signup.id}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "answers" not in data, "custom-form answers must not be exposed with no auth"
        assert "volunteer_id" not in data, "volunteer identity must not be exposed with no auth"
        assert str(volunteer.id) not in str(data)
        assert "peanut allergy" not in str(data), "answer value leaked into the response"

    def test_response_still_has_what_the_check_in_page_needs(self, client, db_session):
        event, slot, signup, volunteer = self._make_signup_with_answer(db_session)

        resp = client.get(f"/api/v1/signups/{signup.id}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["event_id"] == str(event.id)
        assert data["event_title"] == event.title
        assert data["status"] == "confirmed"

    def test_unknown_signup_404s(self, client, db_session):
        resp = client.get(f"/api/v1/signups/{uuid.uuid4()}")
        assert resp.status_code == 404
