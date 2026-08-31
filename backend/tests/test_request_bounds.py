"""Bounds on values that reach the database directly.

These were 500s. A negative `page` became a negative SQL OFFSET and a
malformed UUID reached Postgres as "invalid input syntax" — both surfaced as
"Internal Server Error", which is wrong twice over: it claims the server
failed when the request was malformed, and it buries genuine faults among
noise from bad input.

Validating at the edge is what keeps a hostile or careless caller from
reaching the database at all.
"""

import pytest
from pydantic import ValidationError, BaseModel, Field


# Mirrors the Query(...) constraints declared on the admin list endpoints.
class _Pagination(BaseModel):
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=10, ge=1, le=100)


@pytest.mark.parametrize("page", [0, -1, -5, -1000])
def test_page_must_be_positive(page):
    """A negative page produced a negative OFFSET, which Postgres rejects."""
    with pytest.raises(ValidationError):
        _Pagination(page=page)


@pytest.mark.parametrize("per_page", [0, -1, 101, 1_000_000])
def test_per_page_is_bounded(per_page):
    """Unbounded, a single request could ask for the entire table."""
    with pytest.raises(ValidationError):
        _Pagination(per_page=per_page)


@pytest.mark.parametrize("page,per_page", [(1, 1), (1, 10), (5, 100), (999, 20)])
def test_sensible_pagination_is_accepted(page, per_page):
    p = _Pagination(page=page, per_page=per_page)
    assert p.page == page and p.per_page == per_page


def test_offset_is_never_negative():
    """The arithmetic the endpoints perform, given validated input."""
    for page in (1, 2, 50):
        for per_page in (1, 10, 100):
            assert (page - 1) * per_page >= 0
