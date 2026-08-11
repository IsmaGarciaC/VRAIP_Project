"""
Batch ingestion of manually retrieved historical IG-EPN bulletins.

Why this exists
---------------
The live scraper (modules/scraper.py) only ever reaches the newest report on
the first page of the IG-EPN results list, so building a sample of real
bulletins through main.py would mean waiting on the source's daily publication
cadence. This script takes PDFs that were downloaded by hand from the portal's
paginated history and pushes them through the exact same Stages 2-4 the live
pipeline uses, so the sample can be assembled from the existing archive.

It deliberately does NOT touch Stage 1: no Selenium, no browser, no network.

Provenance
----------
Everything ingested here is stamped with SOURCE_URL, which marks the row as
manually retrieved. That is the only thing distinguishing these bulletins from
live-scraped ones in the database, and it is what lets the write-up separate
evidence produced by the live automated pipeline from bulletins that were only
used to build up the historical sample.

Usage
-----
    python scripts/ingest_historical.py
    python scripts/ingest_historical.py --folder data/historical
    python scripts/ingest_historical.py --manifest /path/to/manifest.csv

The folder must contain a manifest listing which volcano each PDF belongs to,
because the downloaded filenames carry no reliable volcano information:

    filename,volcano_name
    reventador_informe_220.pdf,Reventador
    sangay_informe_018.pdf,Sangay
"""

import os
import sys
import csv
import time
import argparse
import traceback
from datetime import datetime

# This script lives one level deeper than main.py, so the project root has to
# go on the path before the pipeline packages can be imported.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Tee is imported rather than re-implemented so both entry points keep writing
# logs the same way; main.py stays untouched.
from main import Tee
from modules.ingestion import ingest_pdf
from modules.classifier import process_classification
from modules.interpreter import process_interpretation
from database.db import get_all_volcanoes

LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
DEFAULT_FOLDER = os.path.join(PROJECT_ROOT, "data", "historical")
MANIFEST_NAME = "manifest.csv"

REQUIRED_COLUMNS = ("filename", "volcano_name")

# Stored verbatim in bulletins.source_url. Live runs store the real portal URL
# (or the fallback marker), so this string is what separates the two origins.
SOURCE_URL = (
    "Historical archive - manually retrieved from IG-EPN portal "
    "(https://www.igepn.edu.ec/servicios/busqueda-informes)"
)


def read_manifest(manifest_path):
    """
    Parses the manifest into a list of (line_number, filename, volcano_name).

    Blank lines and lines whose filename starts with '#' are skipped so the file
    can be annotated by hand. Raises if the file is missing or lacks the
    required columns — a malformed manifest is a setup error, not a per-row
    failure, so it must stop the batch instead of being isolated.
    """
    if not os.path.isfile(manifest_path):
        raise FileNotFoundError(
            f"Manifest not found: {manifest_path}\n"
            f"    Create it with a header row and one line per PDF:\n"
            f"        filename,volcano_name\n"
            f"        reventador_informe_220.pdf,Reventador"
        )

    # utf-8-sig so a BOM from Excel/LibreOffice does not corrupt the first header.
    with open(manifest_path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = [(name or "").strip() for name in (reader.fieldnames or [])]

        missing = [c for c in REQUIRED_COLUMNS if c not in fieldnames]
        if missing:
            raise ValueError(
                f"Manifest {manifest_path} is missing required column(s): "
                f"{', '.join(missing)}. Found: {', '.join(fieldnames) or '(none)'}"
            )

        rows = []
        for line_number, raw in enumerate(reader, start=2):  # line 1 is the header
            filename = (raw.get("filename") or "").strip()
            volcano_name = (raw.get("volcano_name") or "").strip()

            if not filename and not volcano_name:
                continue
            if filename.startswith("#"):
                continue

            rows.append((line_number, filename, volcano_name))

    return rows


def process_manifest_row(filename, volcano_name, folder, volcano_ids):
    """
    Runs Stages 2-4 for a single manifest row.
    Returns (success: bool, ai_id or None).

    Mirrors main.py's run_pipeline_for_volcano: every failure is caught and
    reported here with a full traceback, so one unreadable or mislabelled PDF
    can never abort the rest of the batch.
    """
    try:
        if not filename:
            raise ValueError("Manifest row has an empty 'filename'.")
        if not volcano_name:
            raise ValueError(f"Manifest row for '{filename}' has an empty 'volcano_name'.")

        volcano_id = volcano_ids.get(volcano_name.lower())
        if volcano_id is None:
            available = ", ".join(sorted(v.title() for v in volcano_ids))
            raise ValueError(
                f"'{volcano_name}' is not a seeded volcano. Available: {available}"
            )

        pdf_path = os.path.join(folder, filename)
        if not os.path.isfile(pdf_path):
            raise FileNotFoundError(f"PDF listed in the manifest does not exist: {pdf_path}")

        # Stage 2: Ingestion.
        # ingest_pdf raises ValueError when the extracted text does not mention
        # volcano_name, which is exactly the guard a hand-written manifest needs:
        # a mistyped or swapped mapping is rejected instead of being stored under
        # the wrong volcano_id.
        print("\n[>>> STAGE 2: TEXT EXTRACTION <<<]")
        bulletin_id = ingest_pdf(pdf_path, volcano_id, volcano_name, SOURCE_URL)

        if not bulletin_id:
            raise Exception("The text extraction process failed.")

        # Stage 3: Classification
        print("\n[>>> ETAPA 3: CLASIFICACIÓN TÉCNICA <<<]")
        class_id = process_classification(bulletin_id)

        if not class_id:
            raise Exception("The clasification process failed.")

        # Stage 4: Interpretation
        print("\n[>>> STAGE 4: Interpretation <<<]")
        ai_id = process_interpretation(class_id)

        if not ai_id:
            raise Exception("The AI module failed.")

        print("\n" + "=" * 50)
        print(" [✓] HISTORICAL BULLETIN INGESTED ")
        print(f" [✓] bulletin_id={bulletin_id}  class_id={class_id}  ai_id={ai_id}")
        print("=" * 50 + "\n")

        return True, ai_id

    except Exception:
        print("\n" + "=" * 50)
        print(f" [X] CRITICAL ERROR OCCURRED — File: {filename} | Volcano: {volcano_name}")
        print(traceback.format_exc())
        print("=" * 50 + "\n")
        return False, None


def parse_args():
    parser = argparse.ArgumentParser(
        description="VRAIP: batch-ingest manually retrieved historical bulletins "
                    "(Stages 2-4 only, no scraping)."
    )
    parser.add_argument(
        "--folder",
        default=DEFAULT_FOLDER,
        help=f"Folder holding the downloaded PDFs (default: {DEFAULT_FOLDER}).",
    )
    parser.add_argument(
        "--manifest",
        help=f"Path to the manifest CSV (default: <folder>/{MANIFEST_NAME}).",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    folder = os.path.abspath(args.folder)
    manifest_path = os.path.abspath(args.manifest) if args.manifest \
        else os.path.join(folder, MANIFEST_NAME)

    # Same dual-output logging as main.py, into its own historical_*.log file so
    # these batches never get confused with live pipeline runs.
    os.makedirs(LOGS_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(LOGS_DIR, f"historical_{timestamp}.log")
    log_file = open(log_path, "a", encoding="utf-8")
    original_stdout = sys.stdout
    sys.stdout = Tee(original_stdout, log_file)

    try:
        print("\n" + "=" * 50)
        print(" VRAIP: HISTORICAL BULLETIN BATCH INGESTION ")
        print("=" * 50 + "\n")
        print(f"[LOG] Run started: {timestamp}")
        print(f"[LOG] Writing full run log to: {log_path}")
        print(f"[*] PDF folder: {folder}")
        print(f"[*] Manifest:   {manifest_path}")
        print(f"[*] Stages: 2 (ingestion) -> 3 (classification) -> 4 (interpretation).")
        print(f"[*] Scraping is skipped; every row is stamped source_url=\"{SOURCE_URL}\"")

        if not os.path.isdir(folder):
            print(f"\n[X] PDF folder does not exist: {folder}")
            return

        # Setup errors (bad manifest, uninitialised DB) stop the batch: unlike a
        # single bad PDF, there is nothing left to isolate.
        try:
            rows = read_manifest(manifest_path)
        except Exception as e:
            print(f"\n[X] {e}")
            return

        volcanoes = get_all_volcanoes()
        if not volcanoes:
            print("\n[X] No volcanoes are seeded in the database.")
            print("    Run 'python database/db.py' first to create and seed it.")
            return

        volcano_ids = {name.lower(): vid for vid, name in volcanoes}

        if not rows:
            print(f"\n[X] Manifest {manifest_path} lists no PDFs to ingest.")
            return

        total = len(rows)
        succeeded = 0
        failed = 0
        failures = []
        run_start = time.time()

        print(f"\n[*] {total} bulletin(s) listed in the manifest.")

        for index, (line_number, filename, volcano_name) in enumerate(rows, start=1):
            print("\n" + "#" * 50)
            print(f" [{index}/{total}] {filename} -> {volcano_name} (manifest line {line_number}) ")
            print("#" * 50)

            start = time.time()
            success, _ai_id = process_manifest_row(filename, volcano_name, folder, volcano_ids)
            elapsed = time.time() - start

            print(f"[TIME] {filename}: {elapsed:.2f}s")

            if success:
                succeeded += 1
            else:
                failed += 1
                failures.append((line_number, filename, volcano_name))

        total_elapsed = time.time() - run_start

        # Final summary.
        print("\n" + "=" * 50)
        print(" HISTORICAL INGESTION SUMMARY ")
        print("=" * 50)
        print(f" Bulletins processed: {total}")
        print(f" Succeeded:           {succeeded}")
        print(f" Failed:              {failed}")
        print(f" Total elapsed time:  {total_elapsed:.2f}s")
        print(f" Log file:            {log_path}")

        if failures:
            print("\n Failed rows (see tracebacks above):")
            for line_number, filename, volcano_name in failures:
                print(f"   - line {line_number}: {filename} ({volcano_name})")

        print("=" * 50 + "\n")

    finally:
        # Always restore stdout and close the log file, even on unexpected errors.
        sys.stdout = original_stdout
        log_file.close()


if __name__ == "__main__":
    main()
