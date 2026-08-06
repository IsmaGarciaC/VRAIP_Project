"""Integration test for the Gemini interpreter module.

This calls the real Gemini API and reads/writes the SQLite DB, so it needs a
valid GEMINI_API_KEY and an existing classification row (id=1). It is marked
`integration` and is deselected by `pytest -m "not integration"`.

Imports of `modules.interpreter` / `database.db` are deferred into the test
body on purpose: `modules.interpreter` raises ValueError at import time when
GEMINI_API_KEY is missing, so importing it at module scope would break
collection (and therefore the offline `-m "not integration"` run) too.

Can still be run manually as a script:
    python tests/test_interpreter.py
"""

import sqlite3

import pytest


@pytest.mark.integration
def test_process_interpretation_saves_structured_alert():
    from database.db import DB_PATH
    from modules.interpreter import process_interpretation

    class_id = 1  # requires an existing classification row in the DB
    new_ai_id = process_interpretation(class_id)
    assert new_ai_id is not None

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT explanation, recommendations FROM ai_alerts WHERE id = ?",
        (new_ai_id,),
    )
    row = cursor.fetchone()
    conn.close()

    assert row is not None
    assert len(row[0].strip()) > 0   # explanation is non-empty
    assert len(row[1].strip()) > 0   # recommendations is non-empty


if __name__ == "__main__":
    # Allow running directly (`python tests/test_interpreter.py`) for manual checks.
    test_process_interpretation_saves_structured_alert()
