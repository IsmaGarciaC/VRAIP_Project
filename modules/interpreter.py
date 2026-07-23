import os
import sqlite3
from google import genai
from dotenv import load_dotenv

# 1. Load the API Key securely
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY or GEMINI_API_KEY == "your_gemini_api_key_here":
    raise ValueError("ERROR: Please insert a valid Gemini API Key in your .env file.")

# Initialize the Google GenAI Client
client = genai.Client(api_key=GEMINI_API_KEY)

# Absolute path to the database file
DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "vraip.db"))

def get_classification_data(class_id):
    """Retrieves classification data joined with the volcano's name from the database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.id, v.name, c.alert_level, c.surface_activity, c.ash_emissions
            FROM classifications c
            JOIN bulletins b ON c.bulletin_id = b.id
            JOIN volcanoes v ON b.volcano_id = v.id
            WHERE c.id = ?
        """, (class_id,))
        result = cursor.fetchone()
        conn.close()
        return result
    except Exception as e:
        print(f"[-] Error retrieving classification data: {e}")
        return None

def use_fallback_ai(volcano_name, alert_level):
    """Emergency Fallback Protocol ensures the pipeline continues if API quota is 0."""
    print("    [*] (Fallback) Activating emergency protocol: Using pre-calculated AI interpretation.")
    return f"""
    EXPLANATION:
    The current technical data for {volcano_name} indicates heightened volcanic activity, matching a {alert_level} status. This presents an elevated risk of ashfall and gas exposure in the surrounding areas, potentially disrupting daily life.

    RECOMMENDATIONS:
    - Wear N95 masks and protective eyewear when outdoors to prevent respiratory and eye irritation.
    - Seal windows and doors with damp towels to minimize the ingress of volcanic ash into homes.
    - Stay tuned to official IGEPN broadcasts and prepare an emergency kit with basic supplies.
    """

def generate_ai_interpretation(volcano_name, alert_level, activity_type, emissions_flag):
    """Generates AI interpretation or falls back to emergency protocol."""
    models_to_test = ["gemini-2.0-flash", "gemini-1.5-flash"]
    emissions_context = "with ash and gas emissions" if emissions_flag else "without significant emissions"
    
    prompt = f"""
    You are a disaster risk management expert from Ecuador. Your goal is to translate 
    technical volcanic alerts into clear, citizen-friendly language.
    
    Current Context:
    - Volcano: {volcano_name}
    - Technical Alert Level: {alert_level}
    - Activity: {activity_type} {emissions_context}.
    
    IMPORTANT: You must write the output entirely in ENGLISH using exactly this format:
    
    EXPLANATION:
    (Write 2 simple sentences explaining what this technical data means for the local population).
    
    RECOMMENDATIONS:
    - (Preventive action 1)
    - (Preventive action 2)
    - (Preventive action 3)
    """
    
    for model_name in models_to_test:
        try:
            print(f"[*] Attempting connection with {model_name}...")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            print(f"[+] Successful connection with {model_name}!")
            return response.text
            
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg:
                print(f"    [-] Rate limit or Quota restriction hit for {model_name}.")
            else:
                print(f"    [-] Connection error with {model_name}: {type(e).__name__}")
            continue
            
    print("\n[-] All live AI connections failed.")
    return use_fallback_ai(volcano_name, alert_level)

def save_ai_alert(classification_id, explanation, recommendations):
    """Saves the parsed AI response into the ai_alerts table."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO ai_alerts (classification_id, explanation, recommendations)
            VALUES (?, ?, ?)
        """, (classification_id, explanation, recommendations))
        conn.commit()
        ai_id = cursor.lastrowid
        conn.close()
        return ai_id
    except Exception as e:
        print(f"[-] Error saving AI alert to DB: {e}")
        return None

def process_interpretation(class_id):
    """Master function to orchestrate the AI interpretation and database storage."""
    print(f"[*] Fetching data for Classification ID: {class_id}...")
    data = get_classification_data(class_id)
    
    if not data:
        print("[-] Classification data not found.")
        return None
        
    c_id, volc_name, alert, act_type, em_flag = data
    print(f"[*] Generating AI citizen alert for '{volc_name}' (Alert: {alert})...")
    
    ai_response = generate_ai_interpretation(volc_name, alert, act_type, em_flag)
    
    if not ai_response:
        return None
        
    if "RECOMMENDATIONS:" in ai_response and "EXPLANATION:" in ai_response:
        parts = ai_response.split("RECOMMENDATIONS:")
        explanation = parts[0].replace("EXPLANATION:", "").strip()
        recommendations = parts[1].strip()
        
        print("[*] Parsing successful. Saving interpretation to 'ai_alerts' table...")
        new_id = save_ai_alert(class_id, explanation, recommendations)
        
        if new_id:
            print(f"[+] SUCCESS! Citizen alert saved with ID: {new_id}")
            return new_id
    else:
        print("[-] Error: AI did not return the expected structured format.")
        
    return None
