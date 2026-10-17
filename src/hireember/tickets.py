"""Ticket data layer: statuses, history, scoring tickets and duplicate checks."""

import re

ALLOWED_STATUSES: tuple[str, ...] = (
    "pending", "started", "applying", "blocked for human", "applied", "skipped", "closed",
)


class TicketError(Exception):
    """Base class for ticket errors."""


class InvalidStatusError(TicketError, ValueError):
    """A status outside ALLOWED_STATUSES was requested."""

    def __init__(self, value: object):
        super().__init__(
            f"Invalid status {value!r}. Allowed statuses: {', '.join(ALLOWED_STATUSES)}."
        )


class TicketNotFoundError(TicketError):
    """No ticket with the given id."""

    def __init__(self, ticket_id: int):
        super().__init__(f"Ticket {ticket_id} not found.")


class DuplicateTicketError(TicketError):
    """The ticket duplicates a ticket that is already in progress or done."""

    def __init__(self, ticket_id: int, duplicate_of: int):
        self.ticket_id = ticket_id
        self.duplicate_of = duplicate_of
        super().__init__(f"Ticket {ticket_id} is a duplicate of ticket {duplicate_of}; not started.")


class OverrideReasonError(TicketError):
    """An override was requested without a reason."""

    def __init__(self):
        super().__init__("An override needs a reason.")


_PUNCT = re.compile(r"[^\w\s]|_", re.UNICODE)


def normalize_text(value: str | None) -> str:
    """Lowercase, replace punctuation with a space, collapse whitespace, trim."""
    if not value:
        return ""
    return " ".join(_PUNCT.sub(" ", str(value).lower()).split())
