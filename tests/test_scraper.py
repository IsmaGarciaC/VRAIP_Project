"""Integration test for the IG-EPN scraper.

This drives a live headless-browser scrape of the IG-EPN portal, so it needs
network access and cannot run in CI/offline. It is marked `integration` and is
deselected by `pytest -m "not integration"`.

The `modules.scraper` import (which pulls in Selenium) is deferred into the test
body so that collecting this file never fails when Selenium isn't installed.

Can still be run manually as a script for the human-readable output:
    python tests/test_scraper.py
"""

import os

import pytest


@pytest.mark.integration
def test_get_latest_bulletin_returns_valid_path():
    from modules.scraper import get_latest_bulletin

    print("\n========================================")
    print(" SCRAPER INTEGRATION TEST (IG-EPN)      ")
    print("========================================")

    file_path, file_name, source_url = get_latest_bulletin("Reventador")

    print(f"[+] file_name : {file_name}")
    print(f"[+] file_path : {file_path}")
    print(f"[+] source_url: {source_url}")
    print("========================================")

    assert file_path is not None
    assert file_name is not None
    assert os.path.exists(file_path)
    # A real, successful scrape returns the live IG-EPN https URL; the offline
    # fallback returns a non-http marker string, so this also guards against a
    # silent fallback masquerading as success.
    assert source_url is not None and source_url.startswith("http")


if __name__ == "__main__":
    # Allow running directly (`python tests/test_scraper.py`) for manual checks.
    test_get_latest_bulletin_returns_valid_path()
