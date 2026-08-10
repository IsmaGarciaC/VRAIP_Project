import os
import sys
import time
import argparse
import traceback
from datetime import datetime

# Add the current directory to the path to avoid import issues
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from modules.scraper import get_latest_bulletin
from modules.ingestion import ingest_pdf
from modules.classifier import process_classification
from modules.interpreter import process_interpretation
from database.db import get_all_volcanoes

# Directory where per-run log files are written.
LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")


class Tee:
    """Duplicates every write to several streams at once.

    Used to mirror everything printed to stdout (including the print() output
    of the untouched pipeline modules and any tracebacks) into a log file,
    while still showing it live in the terminal. Flushes on every write so the
    log stays complete even if the process dies mid-run.
    """

    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for stream in self.streams:
            stream.write(data)
            stream.flush()
        return len(data)

    def flush(self):
        for stream in self.streams:
            stream.flush()


def run_pipeline_for_volcano(volcano_name, volcano_id):
    """Runs the 4-stage pipeline for a single volcano.
    Returns (success: bool, ai_id or None)."""
    try:
        # Stage 1: Scraping
        print("\n[>>> STAGE 1: DATA SCRAPING <<<]")
        pdf_path, pdf_name, source_url = get_latest_bulletin(volcano_name)

        if not pdf_path:
            raise Exception("The scrapper could not retrieve the latest bulletin.")

        # Stage 2: Ingestion
        print("\n[>>> STAGE 2: TEXT EXTRACTION <<<]")
        bulletin_id = ingest_pdf(pdf_path, volcano_id, volcano_name, source_url)

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

        print("\n" + "="*50)
        print(" [✓] PIPELINE SUCCESSFULLY COMPLETED ")
        print(f" [✓] Final data saved in: (ID: {ai_id})")
        print("="*50 + "\n")

        return True, ai_id

    except Exception as e:
        print("\n" + "="*50)
        print(f" [X] CRITICAL ERROR OCCURRED — Volcano: {volcano_name}")
        print(traceback.format_exc())
        print("="*50 + "\n")
        return False, None


def parse_args():
    parser = argparse.ArgumentParser(
        description="VRAIP: Volcanic Risk AI Pipeline."
    )
    parser.add_argument(
        "--volcano",
        help="Run the pipeline for a single volcano by name "
             "(default: run every seeded volcano).",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Set up dual-output logging: everything printed to stdout is also written
    # to a timestamped plain-text log file under logs/.
    os.makedirs(LOGS_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(LOGS_DIR, f"run_{timestamp}.log")
    log_file = open(log_path, "a", encoding="utf-8")
    original_stdout = sys.stdout
    sys.stdout = Tee(original_stdout, log_file)

    try:
        print("\n" + "="*50)
        print(" VRAIP: VOLCANIC RISK AI PIPELINE - SYSTEM START ")
        print("="*50 + "\n")
        print(f"[LOG] Run started: {timestamp}")
        print(f"[LOG] Writing full run log to: {log_path}")

        # Decide which volcanoes to process.
        all_volcanoes = get_all_volcanoes()

        if args.volcano:
            volcanoes = [
                (vid, name) for (vid, name) in all_volcanoes
                if name.lower() == args.volcano.lower()
            ]
            if not volcanoes:
                available = ", ".join(name for _, name in all_volcanoes)
                print(f"\n[X] No seeded volcano named '{args.volcano}'.")
                print(f"    Available volcanoes: {available}")
                return
        else:
            volcanoes = all_volcanoes

        total = len(volcanoes)
        succeeded = 0
        failed = 0
        run_start = time.time()

        # Loop over volcanoes. A failure inside run_pipeline_for_volcano is
        # caught there and returned as success=False, so one volcano's failure
        # never stops the others from running.
        for volcano_id, volcano_name in volcanoes:
            print("\n" + "#"*50)
            print(f" PROCESSING VOLCANO: {volcano_name} (ID: {volcano_id}) ")
            print("#"*50)

            start = time.time()
            success, ai_id = run_pipeline_for_volcano(volcano_name, volcano_id)
            elapsed = time.time() - start

            print(f"[TIME] {volcano_name}: {elapsed:.2f}s")

            if success:
                succeeded += 1
            else:
                failed += 1

        total_elapsed = time.time() - run_start

        # Final summary.
        print("\n" + "="*50)
        print(" RUN SUMMARY ")
        print("="*50)
        print(f" Volcanoes processed: {total}")
        print(f" Succeeded:           {succeeded}")
        print(f" Failed:              {failed}")
        print(f" Total elapsed time:  {total_elapsed:.2f}s")
        print(f" Log file:            {log_path}")
        print("="*50 + "\n")

    finally:
        # Always restore stdout and close the log file, even on unexpected errors.
        sys.stdout = original_stdout
        log_file.close()


if __name__ == "__main__":
    main()
