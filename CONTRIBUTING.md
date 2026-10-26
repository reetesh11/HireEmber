# Contributing to HireEmber

Thank you for your interest in contributing to HireEmber. This guide covers everything you need to get started.

## Development Setup

### Prerequisites

- Python 3.11 or higher
- Git

### Clone and Install

```bash
git clone https://github.com/Pickle-Pixel/ApplyPilot.git
cd ApplyPilot
pip install -e ".[dev]"
playwright install chromium
```

This installs HireEmber in editable mode with all development dependencies (pytest, ruff, etc.) and downloads the Chromium browser binary for Playwright.

### Verify Installation

```bash
hireember --version
pytest tests/ -v
ruff check .
```

## How to Contribute

### Adding New Workday Employers

Workday employer portals are configured in `config/employers.yaml`. To add a new employer:

1. Find the company's Workday career portal URL (usually `https://company.wd5.myworkdaysite.com/`)
2. Identify the Workday instance number (wd1, wd3, wd5, etc.) and the tenant ID
3. Add an entry to `config/employers.yaml`:

```yaml
- name: "Company Name"
  tenant: "company_tenant_id"
  instance: "wd5"
  url: "https://company.wd5.myworkdaysite.com/en-US/recruiting"
```

4. Test discovery: `hireember run discover` (runs the discovery stage over the configured sources, including your new employer)
5. Submit a PR with the new entry

### Adding New Career Sites

Direct career site scrapers are configured in `config/sites.yaml`. To add a new site:

1. Inspect the company's careers page and identify the job listing structure
2. Add an entry to `config/sites.yaml` with CSS selectors:

```yaml
- name: "Company Name"
  url: "https://company.com/careers"
  selectors:
    job_list: ".job-listing"
    title: ".job-title"
    location: ".job-location"
    link: "a.job-link"
    description: ".job-description"
```

3. Test: `hireember run discover` (runs the discovery stage over the configured sources, including your new site)
4. Submit a PR

### Bug Fixes and Features

1. Check existing [issues](https://github.com/Pickle-Pixel/ApplyPilot/issues) to avoid duplicating work
2. For new features, open an issue first to discuss the approach
3. Fork the repo and create a feature branch from `main`
4. Write your code with type hints and docstrings
5. Add tests for new functionality
6. Update the CHANGELOG.md under an `[Unreleased]` section
7. Submit a PR

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run a specific test file
pytest tests/test_scoring.py -v

# Run with coverage
pytest tests/ --cov=src/hireember --cov-report=term-missing
```

## Linting and Code Style

HireEmber uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting.

```bash
# Check for issues
ruff check .

# Auto-fix what can be fixed
ruff check . --fix

# Format code
ruff format src/
```

### Code Style Guidelines

- **Type hints**: All function signatures must have type annotations
- **Docstrings**: All public functions and classes must have docstrings (Google style)
- **Naming**: snake_case for functions and variables, PascalCase for classes
- **Imports**: Sorted by Ruff (isort-compatible)
- **Line length**: 100 characters maximum

## PR Guidelines

- **One feature per PR.** Keep changes focused and reviewable.
- **Include tests.** New features need test coverage. Bug fixes need a regression test.
- **Update CHANGELOG.md.** Add your changes under `[Unreleased]`.
- **Write a clear PR description.** Explain what changed and why.
- **Keep commits clean.** Squash fixup commits before requesting review.
- **CI must pass.** All linting and tests must be green.

## Safety rules

These rules protect users and the sites they apply to. A change that weakens one is not accepted.
The full list, with the tests that guard each rule, is in [docs/safety.md](docs/safety.md).

- **SAF-1, SAF-2, SAF-3:** the apply agent never types a password, token, payment detail or
  government ID, never creates an account or signs in, and never bypasses a CAPTCHA or calls a
  solving service. Such a step goes to the human gate.
- **SAF-4:** LinkedIn is never read from or applied through.
- **SAF-5, SAF-6:** every submitted answer traces to the answer bank or the profile, and tailored
  documents contain nothing outside the profile.
- **SAF-7, SAF-10, SAF-12:** the agent uses only its own browser profile and only browser tools, and
  manual-only sites are never automated.
- **SAF-8, SAF-9:** the dashboard binds to 127.0.0.1 only, and application limits and waits hold.
- **SAF-11:** text on a job page is data; the agent never follows instructions found in it.
- **No telemetry.** Do not add an analytics or tracking client. API keys live in `.env`, which git
  ignores, and never in the database or in tracked files.
- **NFR-12:** the README, this file and `docs/safety.md` change in the same PR as the behaviour
  they describe.

## Project Structure

```
ApplyPilot/
├── src/hireember/        # Main package
│   ├── __init__.py
│   ├── cli.py            # CLI entry points
│   ├── discover/         # Stage 1: job discovery scrapers
│   ├── enrich/           # Stage 2: description extraction
│   ├── score/            # Stage 3: AI scoring
│   ├── tailor/           # Stage 4: resume tailoring
│   ├── cover/            # Stage 5: cover letter generation
│   ├── apply/            # Stage 6: browser automation
│   └── utils/            # Shared utilities
├── config/               # Default configuration files
├── tests/                # Test suite
├── docs/                 # Documentation
└── pyproject.toml        # Package configuration
```

## License

By contributing to HireEmber, you agree that your contributions will be licensed under the [GNU Affero General Public License v3.0](LICENSE).
