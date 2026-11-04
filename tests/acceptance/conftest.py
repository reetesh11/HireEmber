"""Fixtures for the acceptance tests added in phase 10."""

import pytest


@pytest.fixture
def conn(isolated_db):
    """A fresh initialised database connection (temp file) with the data folders created."""
    from hireember import config
    from hireember.database import close_connection, init_db

    c = init_db(isolated_db)
    config.ensure_dirs()
    yield c
    close_connection(isolated_db)
