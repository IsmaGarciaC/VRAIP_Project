import os
import pdfplumber
import sqlite3
import unicodedata
from datetime import datetime

# Absolute path to the database file.
# VRAIP_DB_PATH overrides it so verification runs can be pointed at a throwaway
# copy instead of writing into the live database.
DB_PATH = os.getenv(
    "VRAIP_DB_PATH",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "vraip.db")),
)

def normalize_text(text):
    """
    Lowercases and strips accents so bulletin text can be compared against a
    volcano name regardless of casing or how the PDF encodes its diacritics
    ('Volcán'/'VOLCAN', 'Sangay'/'SANGAY').
    """
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))

def extract_text_from_pdf(pdf_path):
    """
    Extracts PDF text using pdfplumber.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"The file {pdf_path} does not exist.")

    complete_text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                extracted_text = page.extract_text()
                if extracted_text:
                    complete_text += extracted_text + "\n"
        return complete_text

    # Handle any exceptions that may occur during PDF processing
    except Exception as e:
        raise Exception(f"Failed to extract text from {pdf_path}. Error: {e}")

# Function to save extracted text to a SQLite database
def save_bulletin_to_db(volcano_id, raw_text, pdf_filename, source_url):
    """
    Saves the extracted bulletin data to the SQLite database.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Save the exact date and time of extraction
        published_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Insert the data into the database
        cursor.execute("""
            INSERT INTO bulletins (volcano_id, published_at, source_url, raw_text, pdf_filename)
            VALUES (?, ?, ?, ?, ?)
        """, (volcano_id, published_at, source_url, raw_text, pdf_filename))

        conn.commit()
        bulletin_id = cursor.lastrowid
        conn.close()

        return bulletin_id

    # Handle any exceptions that may occur during database operations
    except Exception as e:
        print(f"[-] Error: Failed to save bulletin data to the database. Error: {e}")
        return None

# Function to ingest a PDF file into the database
def ingest_pdf(pdf_path, volcano_id, volcano_name, source_url="Local Ingestion (Offline)"):
    """
    Master function to orchestrate text extraction and database ingestion.
    Returns the new bulletin_id if successful, None otherwise.

    Raises ValueError if the extracted text does not mention volcano_name, which
    means the PDF belongs to a different volcano (a stale or mismatched file) and
    must never be stored under this volcano_id.
    """
    file_name = os.path.basename(pdf_path)
    print(f"[*] Extracting text from '{file_name}'...")

    # Extract text from the PDF file
    try:
        raw_text = extract_text_from_pdf(pdf_path)

    # Handle any exceptions that may occur during text extraction
    except Exception as e:
        print(f"[-] Ingestion failed: {e}")
        return None

    # Content-level sanity check. Deliberately raises instead of returning None:
    # a mismatch is a data-integrity problem, and main.py's run_pipeline_for_volcano
    # already logs the full traceback and isolates the failure to this volcano.
    if normalize_text(volcano_name) not in normalize_text(raw_text):
        raise ValueError(
            f"Extracted text does not mention '{volcano_name}' — "
            f"likely mismatched or stale file: {pdf_path}"
        )

    print(f"[*] Text extracted successfully ({len(raw_text)} characters). Saving to DB...")

    bulletin_id = save_bulletin_to_db(volcano_id, raw_text, file_name, source_url)

    if bulletin_id:
        print(f"[+] Bulletin ingested correctly in table 'bulletins' with ID: {bulletin_id}")

    return bulletin_id
