import os
import sys

# Add the current directory to the path to avoid import issues
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from modules.scraper import get_latest_bulletin
from modules.ingestion import ingest_pdf
from modules.classifier import process_classification
from modules.interpreter import process_interpretation

def main():
    print("\n" + "="*50)
    print(" VRAIP: VOLCANIC RISK AI PIPELINE - SYSTEM START ")
    print("="*50 + "\n")

    # Initial configuration
    volcano_name = "Reventador"
    volcano_id = 3 

    try:
        # Stage 1: Scraping
        print("\n[>>> STAGE 1: DATA SCRAPING <<<]")
        pdf_path, pdf_name, source_url = get_latest_bulletin(volcano_name)

        if not pdf_path:
            raise Exception("The scrapper could not retrieve the latest bulletin.")

        # Stage 2: Ingestion
        print("\n[>>> STAGE 2: TEXT EXTRACTION <<<]")
        bulletin_id = ingest_pdf(pdf_path, volcano_id, source_url)
        
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

    except Exception as e:
        print("\n" + "="*50)
        print(" [X] CRITICAL ERROR OCCURRED ")
        print(f" Detail: {e}")
        print("="*50 + "\n")

if __name__ == "__main__":
    main()
