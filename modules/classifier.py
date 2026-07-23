import sqlite3
import os
import re

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "vraip.db"))

def get_bulletin_text(bulletin_id):
    """Get the text of a bulletin from the database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT raw_text FROM bulletins WHERE id=?", (bulletin_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    except Exception as e:
        print(f"[-] Error retrieving bulletin text: {e}")
        return None

def classify_risk(raw_text):
    """
    Engine to classify the risk level of a bulletin based on 
    regular expressions to map technical terms to specific metrics.
    """
    text_lower = raw_text.lower()

    # 1. Official alert level
    alert_level = "Yellow Alert"  # Default level
    # Supports line breaks
    alert_match = re.search(r'nivel de alerta\s*[-–:]*\s*(?:sgr)?:?[\s]*([a-záéíóú]+)', text_lower)
    if alert_match:
        raw_alert = alert_match.group(1)
        if "roja" in raw_alert:
            alert_level = "Red Alert"
        elif "naranja" in raw_alert:
            alert_level = "Orange Alert"
        elif "amarilla" in raw_alert:
            alert_level = "Yellow Alert"
        elif "blanca" in raw_alert or "verde" in raw_alert:
            alert_level = "Green Alert"

    # 2. Activity levels
    surface_act = "Not Specified"
    surf_match = re.search(r'superficial:\s*([a-záéíóú]+)', text_lower)
    if surf_match:
        surface_act = surf_match.group(1).strip().title()

    internal_act = "Not Specified"
    int_match = re.search(r'interna:\s*([a-záéíóú]+)', text_lower)
    if int_match:
        internal_act = int_match.group(1).strip().title()

    # 3. Physical Phenomena Detection
    ash_flag = 1 if "ceniza" in text_lower else 0
    gas_flag = 1 if any(kw in text_lower for kw in ["gases", "so2", "dióxido de azufre"]) else 0
    incandescence_flag = 1 if any(kw in text_lower for kw in ["incandescente", "incandescencia"]) else 0

    # 4. Smart detection of Lahar (LAHAR)
    lahar_flag = 0
    if "lahar" in text_lower or "flujo de lodo" in text_lower:
        if not re.search(r'(no\s+(?:se\s+)?(?:registraron|reportaron|observaron)|podrían\s+(?:removilizar|generar))', text_lower):
            lahar_flag = 1

    # 5. Count of Explosions (in the last 24 hours)
    explosions_count = 0
    exp_match = re.search(r'explosió[nñ][\s\|]*\(exp\)[\s\|]*(\d+)', text_lower)
    if exp_match:
        explosions_count = int(exp_match.group(1))

    # 6. Maximum Height of Column Emission (in meters above the crater)
    max_height_m = 0
    heights = re.findall(r'(\d{3,4})\s*(?:m\.s\.n\.c|metros|m\b)', text_lower)
    if heights:
        # Filter heights within a reasonable range (100-20,000 meters)
        valid_heights = [int(h) for h in heights if 100 <= int(h) <= 20000]
        if valid_heights:
            max_height_m = max(valid_heights)

    return {
        "alert_level": alert_level,
        "surface_activity": surface_act,
        "internal_activity": internal_act,
        "ash_emissions": ash_flag,
        "gas_emissions": gas_flag,
        "incandescence": incandescence_flag,
        "lahars_detected": lahar_flag,
        "explosions_count": explosions_count,
        "max_column_height_m": max_height_m
    }

def save_classification(bulletin_id, data):
    """Save the full classification result dictionary to the database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Update SQL to match the 9 extracted variables
        cursor.execute("""
            INSERT INTO classifications (
                bulletin_id, alert_level, surface_activity, internal_activity, 
                ash_emissions, gas_emissions, incandescence, lahars_detected, 
                explosions_count, max_column_height_m
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            bulletin_id, 
            data["alert_level"], 
            data["surface_activity"], 
            data["internal_activity"],
            data["ash_emissions"], 
            data["gas_emissions"], 
            data["incandescence"],
            data["lahars_detected"], 
            data["explosions_count"], 
            data["max_column_height_m"]
        ))

        conn.commit()
        class_id = cursor.lastrowid
        conn.close()
        return class_id
    except Exception as e:
        print(f"[-] Error saving classification: {e}")
        return None

def process_classification(bulletin_id):
    """
    Master orchestrator for the classifier module.
    Extracts text, applies regex rules, and saves the structured data.
    """
    print(f"[*] Extracting raw text for Bulletin ID {bulletin_id}...")
    raw_text = get_bulletin_text(bulletin_id)
    
    if not raw_text:
        print("[-] Classifier Error: Text could not be loaded from DB.")
        return None
        
    print("[*] Running regex classification engine...")
    classification_data = classify_risk(raw_text)
    
    print("[*] Saving structured metrics to database...")
    class_id = save_classification(bulletin_id, classification_data)
    
    if class_id:
        print(f"[+] Classification generated successfully (Class ID: {class_id})")
        return class_id
    else:
        return None
