import pytest

from hireember.tickets import (
    ALLOWED_STATUSES,
    DuplicateTicketError,
    InvalidStatusError,
    TicketError,
    TicketNotFoundError,
    normalize_text,
)


def test_normalize_examples():
    assert normalize_text("  Senior  Engineer (Remote) ") == "senior engineer remote"
    assert normalize_text("New York, NY") == "new york ny"
    assert normalize_text(None) == ""
    assert normalize_text("!!!") == ""


def test_statuses_and_errors():
    assert len(ALLOWED_STATUSES) == 7
    assert "blocked for human" in str(InvalidStatusError("x"))
    assert str(TicketNotFoundError(4)) == "Ticket 4 not found."
    err = DuplicateTicketError(2, 1)
    assert (err.ticket_id, err.duplicate_of) == (2, 1)
    assert isinstance(InvalidStatusError("x"), (TicketError, ValueError))
    with pytest.raises(TicketError):
        raise TicketNotFoundError(1)
