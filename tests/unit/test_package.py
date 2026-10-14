"""Smoke test: the package imports and exposes a version string."""

import applypilot


def test_version_is_non_empty_string():
    assert isinstance(applypilot.__version__, str)
    assert applypilot.__version__
