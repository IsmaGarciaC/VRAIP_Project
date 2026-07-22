import os
import pdfplumber
import sqlite3
from datetime import datetime

# Define the path to the database file
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "vraip.db")

# Define a function to extract text from a PDF file
def extract_text_from_pdf(pdf_path):
    """
    Extracts PDF text using pdfplumber.
    """
    # Check if the file exists before attempting to open it.
    if not os.path.exists(pdf_path):
        return f"Error: The file {pdf_path} does not exist."

    # Open the PDF file and extract text
    complete_text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                extracted_text = page.extract_text()
                if extracted_text:
                    complete_text += extracted_text + "\n"
        return complete_text

        # Handle any exceptions that occur during the extraction process
    except Exception as e:
        return f"Error: Failed to extract text from {pdf_path}. Error: {e}"

# Define a function to save the extracted text to a SQLite database
def save_bulletin_to_db(volcano_id, raw_text, pdf_filename):
    """
        Saves the bulletin data to a SQLite database.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Save the exact date and time of extraction
        published_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        source_url = "Local Ingestion (Offline)"

        # Insert the data into the database
        cursor.execute("""
            INSERT INTO bulletins (volcano_id, published_at, source_url, raw_text, pdf_filename)
            VALUES (?, ?, ?, ?, ?)
        """, (volcano_id, published_at, source_url, raw_text, pdf_filename))

        # Commit the changes and close the connection
        conn.commit()
        bulletin_id = cursor.lastrowid
        conn.close()

        return bulletin_id
    # Handle any exceptions that occur during the database operation
    except Exception as e:
        print(f"Error: Failed to save bulletin data to the database. Error: {e}")
        return None

# Local testing
if __name__ == "__main__":
    # Define the path to the PDF file
    file_name = "boletin_prueba.pdf"
    pdf_path = os.path.join(os.path.dirname(__file__), "..", "data", file_name)

    # Extract text from the PDF
    print(f"[*] Extracting text from {file_name}...")
    text = extract_text_from_pdf(pdf_path)

    # Check if the extraction was successful and proceed accordingly
    if not text.startswith("Error"):
        vocano_id = 3

        print(f"[*] Saving bulletin to database...")
        new_id = save_bulletin_to_db(vocano_id, text, file_name)

        if new_id:
            print(f"\n[*] Bulletin saved correctly in table bulletins with ID: {new_id}")
            print(f"[*] Length of extracted text: {len(text)} characters")
        else:
            print("\n[-] Failed to save bulletin data.")
    else:
        print(text)


