# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

VRAIP (Volcanic Risk AI Pipeline) is a pipeline that scrapes volcanic activity bulletins from Ecuador's IGEPN
(Instituto Geofísico) website, extracts and classifies the technical data, and uses Gemini to translate it into
citizen-friendly alerts in English. Everything is persisted to a local SQLite database.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python database/db.py          # creates data/vraip.db and seeds the `volcanoes` table
cp .env.example .env           # then set GEMINI_API_KEY inside it
```

`modules/interpreter.py` raises `ValueError` at import time if `GEMINI_API_KEY` is missing or left as the
placeholder value, so `.env` must be populated before running anything that imports it (the interpreter module,
`main.py`, or `tests/test_interpreter.py`).

## Running

```bash
python main.py                 # runs the full pipeline: scrape -> ingest -> classify -> interpret
```

There is no test runner/framework configured (no pytest, no config file) — `tests/test_scraper.py` and
`tests/test_interpreter.py` are standalone scripts with `if __name__ == "__main__"` entry points, run directly:

```bash
python tests/test_scraper.py
python tests/test_interpreter.py   # requires classification id 1 to already exist in the DB
```

`app.py` and `style.css` are placeholder stubs for a planned Streamlit frontend (streamlit is not yet in
`requirements.txt` or installed in `.venv`) — do not assume they are functional.

## Architecture

The pipeline is four sequential stages, each writing to one SQLite table, chained together in `main.py`'s
`main()`. Every stage function returns the ID of the row it just created (or `None` on failure), which becomes
the input to the next stage:

1. **Scraping** (`modules/scraper.py`, `get_latest_bulletin(volcano_name)`) — drives headless Chrome via
   Selenium against the IGEPN "búsqueda de informes" form (handles an iframe, three PrimeFaces dropdowns, then
   downloads the report PDF into `data/`). On any exception it falls back to `use_fallback()`, which returns
   the bundled `data/boletin_prueba.pdf` so the rest of the pipeline can still run offline/in demos. Also saves
   a `debug_robot.png` screenshot on failure for diagnosing selector breakage.
2. **Ingestion** (`modules/ingestion.py`, `ingest_pdf(pdf_path, volcano_id)`) — extracts text with `pdfplumber`
   and inserts a row into `bulletins` (raw_text, pdf_filename, published_at). Returns `bulletin_id`.
3. **Classification** (`modules/classifier.py`, `process_classification(bulletin_id)`) — pure regex engine
   (`classify_risk`) over the Spanish bulletin text; no LLM involved. Extracts alert level (Amarilla/Naranja/
   Roja/Blanca-Verde), surface/internal activity, ash/gas/incandescence flags, lahar detection (with negation
   guards for "no se registraron..." phrasing), explosion counts, and max column height. Inserts into
   `classifications`. Returns `class_id`.
4. **Interpretation** (`modules/interpreter.py`, `process_interpretation(class_id)`) — joins
   `classifications -> bulletins -> volcanoes` to get context, then calls Gemini
   (`generate_ai_interpretation`) trying `gemini-2.0-flash` then `gemini-1.5-flash` in order, expecting a
   response with literal `EXPLANATION:` / `RECOMMENDATIONS:` sections that get split and stored. If every model
   call fails (e.g. 429 quota errors), `use_fallback_ai()` returns a canned English explanation/recommendations
   so the pipeline never dead-ends on API limits. Inserts into `ai_alerts`. Returns `ai_id`.

### Database (`database/db.py`)

SQLite at `data/vraip.db` (gitignored), schema created idempotently via `init_db()`'s `CREATE TABLE IF NOT
EXISTS`. Four tables mirror the pipeline stages: `volcanoes` -> `bulletins` -> `classifications` -> `ai_alerts`,
linked by foreign keys. `volcanoes` is seeded once (Cotopaxi, Tungurahua, Reventador, Sangay) only if empty.
Every module recomputes `DB_PATH` independently as `os.path.join(<module dir>, "..", "data", "vraip.db")`
rather than importing a shared constant — keep this pattern in mind if the directory layout changes, since
there's no single source of truth for the path.

`main.py` currently hardcodes `volcano_name = "Reventador"` / `volcano_id = 3`, matching the seed order in
`database/db.py` — if the seed list changes, this id must be updated too.

## Language conventions

Console/log output and some docstrings/comments are a mix of Spanish and English (the domain — IGEPN bulletins,
alert levels — is Spanish; the AI-facing prompt and generated citizen alerts are explicitly forced to English
via the prompt in `modules/interpreter.py`). Match the existing convention in whichever file you're editing
rather than normalizing everything to one language.
