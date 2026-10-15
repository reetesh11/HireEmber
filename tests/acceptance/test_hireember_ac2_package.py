"""Rename AC-2: the package lives at src/hireember and exposes a version string."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_package_directory_is_hireember_only():
    assert (REPO_ROOT / "src" / "hireember").is_dir()
    assert (REPO_ROOT / "src" / "hireember" / "__init__.py").is_file()
    assert not (REPO_ROOT / "src" / "applypilot").exists()


def test_import_hireember_exposes_non_empty_version():
    import hireember

    assert isinstance(hireember.__version__, str)
    assert hireember.__version__ == "0.3.0"
