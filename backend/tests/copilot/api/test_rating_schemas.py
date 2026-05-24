"""Phase 35-01-B Task 4: pydantic rating schema validators."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.copilot.schemas import (
    MessageRatingCreate,
    SessionRatingCreate,
)


def test_message_rating_up_no_comment_ok():
    r = MessageRatingCreate(value="up")
    assert r.value == "up"
    assert r.comment is None


def test_message_rating_down_requires_comment():
    with pytest.raises(ValidationError):
        MessageRatingCreate(value="down")


def test_message_rating_down_whitespace_comment_rejected():
    with pytest.raises(ValidationError):
        MessageRatingCreate(value="down", comment="   ")


def test_message_rating_down_real_comment_ok():
    r = MessageRatingCreate(value="down", comment="wrong week")
    assert r.value == "down"
    assert r.comment == "wrong week"


def test_message_rating_comment_max_length():
    with pytest.raises(ValidationError):
        MessageRatingCreate(value="up", comment="x" * 1001)


def test_session_rating_high_no_comment_ok():
    r = SessionRatingCreate(value=4)
    assert r.value == 4


def test_session_rating_low_requires_comment():
    with pytest.raises(ValidationError):
        SessionRatingCreate(value=2)


def test_session_rating_one_with_comment_ok():
    r = SessionRatingCreate(value=1, comment="lost my data")
    assert r.value == 1
    assert r.comment == "lost my data"


def test_session_rating_value_bounds():
    with pytest.raises(ValidationError):
        SessionRatingCreate(value=0)
    with pytest.raises(ValidationError):
        SessionRatingCreate(value=6)
