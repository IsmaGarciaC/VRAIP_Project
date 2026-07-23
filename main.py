import os
import sys

# Añadir el directorio actual al path para evitar problemas de importación
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from modules.scraper import get_latest_bulletin
from modules.ingestion import ingest_pdf
from modules.classifier import process_classification # Ajusta el nombre si tu función se llama distinto
from modules.interpreter import process_interpretation

def main():
    print("\n" + "="*50)
    print(" VRAIP: VOLCANIC RISK AI PIPELINE - SYSTEM START ")
    print("="*50 + "\n")

    # Configuración inicial
    volcano_name = "Reventador"
    volcano_id = 3 # ID del Reventador en tu tabla 'volcanoes'

    try:
        # --- ETAPA 1: RECOLECCIÓN (Scraping) ---
        print("\n[>>> ETAPA 1: RECOLECCIÓN DE DATOS <<<]")
        pdf_path, pdf_name, source_url = get_latest_bulletin(volcano_name)

        if not pdf_path:
            raise Exception("El scraper no pudo obtener el documento.")

        # --- ETAPA 2: INGESTA (Procesamiento de PDF a BD) ---
        print("\n[>>> ETAPA 2: INGESTA DE DATOS <<<]")
        bulletin_id = ingest_pdf(pdf_path, volcano_id, source_url)
        
        if not bulletin_id:
            raise Exception("Falló la extracción o guardado del texto del PDF.")

        # --- ETAPA 3: CLASIFICACIÓN (Regex a nivel de alerta) ---
        print("\n[>>> ETAPA 3: CLASIFICACIÓN TÉCNICA <<<]")
        class_id = process_classification(bulletin_id)
        
        if not class_id:
            raise Exception("El clasificador no pudo estructurar los datos técnicos.")

        # --- ETAPA 4: INTERPRETACIÓN (Traducción ciudadana con IA) ---
        print("\n[>>> ETAPA 4: INTERPRETACIÓN CIUDADANA <<<]")
        ai_id = process_interpretation(class_id)
        
        if not ai_id:
            raise Exception("El módulo de IA no pudo generar o guardar la alerta.")

        print("\n" + "="*50)
        print(" [✓] PIPELINE COMPLETADO CON ÉXITO ")
        print(f" [✓] Datos finales guardados en ai_alerts (ID: {ai_id})")
        print("="*50 + "\n")

    except Exception as e:
        print("\n" + "="*50)
        print(" [X] ERROR CRÍTICO EN EL PIPELINE ")
        print(f" Detalle: {e}")
        print("="*50 + "\n")

if __name__ == "__main__":
    main()
