import os
import sys

# Make the project root importable so `from modules...` / `from database...`
# resolve no matter how pytest is invoked (pytest tests/, python -m pytest, an
# IDE runner, etc.). Without this, pytest's default "prepend" import mode only
# puts the tests/ directory on sys.path, not the project root.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def pytest_configure(config):
    # Register the custom marker so `-m integration` works and unmarked runs
    # don't emit PytestUnknownMarkWarning.
    config.addinivalue_line(
        "markers", "integration: requires live network/API access"
    )
