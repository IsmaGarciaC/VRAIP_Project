import os
import time
import glob
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# Absolute path to the directory containing the downloaded data
DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))

def get_latest_bulletin(volcano_name):
    """
    Retrieves the latest bulletin for a given volcano from the IGEPN website.
    Uses a headless browser to navigate the form, handle iframes, and download 
    the PDF file into the local data directory.
    """
    url = "https://www.igepn.edu.ec/servicios/busqueda-informes"

    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

    # Robot Configuration
    chrome_options = Options()
    chrome_options.add_argument("--headless=new") 
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    # Preferences for file downloads
    prefs = {
        "download.default_directory": DATA_DIR,
        "download.prompt_for_download": False,
        "plugins.always_open_pdf_externally": True
    }
    chrome_options.add_experimental_option("prefs", prefs)

    print(f"[*] Starting scraping robot at: {url}")

    # WebDriver Setup
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        driver.get(url)
        wait = WebDriverWait(driver, 15)

        print("[*] Connected. Giving the site time to load...")
        time.sleep(4)

        # 1. Iframe Detector
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        if len(iframes) > 0:
            print("[*] Iframe detected! Switching focus to the internal frame...")
            driver.switch_to.frame(iframes[0])
            time.sleep(2)

        # MASTER FUNCTION: Adjusts the view and simulates a human click
        def select_menu(trigger_xpath, option_xpath, wait_time):
            trigger = wait.until(EC.element_to_be_clickable((By.XPATH, trigger_xpath)))
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'auto', block: 'center'});", trigger)
            time.sleep(1)
            trigger.click()
            time.sleep(1.5)

            option = wait.until(EC.element_to_be_clickable((By.XPATH, option_xpath)))
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'auto', block: 'center'});", option)
            time.sleep(1)
            option.click()
            time.sleep(wait_time)

        # --- STEP 1: Type ---
        print("[*] Selecting 'Grupo de Informes Volcánicos'...")
        select_menu(
            "(//*[contains(text(), 'Tipo:') and not(contains(text(), 'informe'))]/following::div[contains(@class, 'ui-selectonemenu-trigger')])[1]", 
            "//li[contains(text(), 'Grupo de Informes Volc')]", 
            4
        )

        # --- STEP 2: Volcano Name ---
        print(f"[*] Selecting volcano: '{volcano_name}'...")
        select_menu(
            "(//*[contains(text(), 'Volcán:')]/following::div[contains(@class, 'ui-selectonemenu-trigger')])[1]", 
            f"//li[contains(text(), '{volcano_name}')]",
            4
        )        

        # --- STEP 3: Current Year ---
        current_year = str(datetime.now().year)
        print(f"[*] Selecting the current year ({current_year})...")
        select_menu(
            "(//*[contains(text(), 'Año:')]/following::div[contains(@class, 'ui-selectonemenu-trigger')])[1]", 
            f"//li[contains(text(), '{current_year}')]", 
            2
        )

        # --- STEP 4: Search ---
        print("[*] Form complete. Executing search...")
        search_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Buscar')]")))
        driver.execute_script("arguments[0].scrollIntoView({behavior: 'auto', block: 'center'});", search_button)
        time.sleep(1)
        search_button.click()

        # --- STEP 5: Download ---
        print("[*] Search completed. Looking for the download button...")
        download_button = wait.until(EC.element_to_be_clickable((By.XPATH, "(//span[contains(text(), 'Descargar Informe')])[1]")))
        driver.execute_script("arguments[0].scrollIntoView({behavior: 'auto', block: 'center'});", download_button)
        time.sleep(1)
        download_button.click()
        
        print("[*] Download button clicked. Waiting for the file to reach the disk...")
        time.sleep(5)

        # --- STEP 6: File validation ---
        pdf_files = glob.glob(os.path.join(DATA_DIR, "*.pdf"))
        if not pdf_files:
            raise FileNotFoundError("The robot clicked download, but the file was not found.")

        newest_file = max(pdf_files, key=os.path.getctime)
        file_name = os.path.basename(newest_file)

        print(f"[+] Automated download successful: '{file_name}'!")
        return newest_file, file_name, url

    # --- STEP 7: Error handling ---
    except Exception as e:
        print(f"[-] Error in the scraping robot: {e}")
        try:
            error_photo_path = os.path.join(DATA_DIR, "debug_robot.png")
            driver.save_screenshot(error_photo_path)
            print(f"[*] 📸 Security camera activated! Screenshot saved at: {error_photo_path}")
        except:
            pass
        return use_fallback()
        
    finally:
        if 'driver' in locals():
            driver.quit()

#--- Fallback Plan ---
def use_fallback():
    """Fallback Plan: Uses a local file if the government website fails or changes."""
    print("[*] (Fallback) Emergency protocol activated: Using local test file.")
    fallback_name = "boletin_prueba.pdf"
    fallback_path = os.path.join(DATA_DIR, fallback_name)
    return fallback_path, fallback_name, "Local Fallback (boletin_prueba.pdf)"
