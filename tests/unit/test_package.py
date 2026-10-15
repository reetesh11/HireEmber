"""Smoke test: the package imports and exposes a version string."""

import hireember


def test_version_is_non_empty_string():
    assert isinstance(hireember.__version__, str)
    assert hireember.__version__
