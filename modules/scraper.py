import os
import time
import glob
import shutil
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

# Previously downloaded PDFs are moved here instead of being deleted, so they
# stay available for debugging a run that went wrong.
ARCHIVE_DIR = os.path.join(DATA_DIR, "_archive")

# Bundled offline/demo bulletin used by use_fallback(). It lives in DATA_DIR
# alongside the downloads but is NOT a download, so it is never archived and
# never counts as the "freshly downloaded" file.
FALLBACK_NAME = "boletin_prueba.pdf"

# --- Results list selectors -------------------------------------------------
# The IGEPN results list mixes file types (PDF reports and PNG infographics)
# in one list sorted by publication date, newest first. Every row renders the
# same button with the same "Descargar Informe" label, and the row classes are
# identical too, so the ONLY machine-readable type signal is the badge image in
# the row's "logo" cell, whose filename encodes the extension:
#     /igepn-registro-web/images/extensiones/PDFB.png  -> PDF report
#     /igepn-registro-web/images/extensiones/PNGB.png  -> PNG infographic
# Matching on "/extensiones/pdf" (lowercased src) rather than the exact
# "PDFB.png" keeps this working if the site ever ships a different size/variant
# of the same badge.
RESULT_ROW_XPATH = "//li[contains(@class, 'ui-dataview-row')]"
TYPE_BADGE_XPATH = ".//td[contains(@class, 'logo')]//img"
PDF_BADGE_MARKER = "/extensiones/pdf"
DOWNLOAD_BUTTON_XPATH = ".//button[.//span[contains(text(), 'Descargar Informe')]]"
REPORT_NAME_XPATH = ".//td[contains(@class, 'detail')]//tr[1]/td[2]//label"


def _report_name(row):
    """Best-effort read of a result row's 'Nombre:' value, for logging only."""
    labels = row.find_elements(By.XPATH, REPORT_NAME_XPATH)
    return labels[0].text.strip() if labels else "(unnamed report)"


def find_first_pdf_download_button(driver, volcano_name, current_year):
    """
    Returns the 'Descargar Informe' button of the newest PDF-type row on the
    results page.

    Rows are already sorted newest-first by the site, so the first PDF-type row
    in document order is the latest PDF report. Non-PDF rows are skipped rather
    than clicked: downloading a PNG infographic leaves DATA_DIR without any new
    *.pdf, which used to send the pipeline into use_fallback() with a stale
    bulletin instead of reporting the real problem.

    Raises FileNotFoundError if no row on the results page is PDF-type.
    """
    rows = driver.find_elements(By.XPATH, RESULT_ROW_XPATH)
    print(f"[*] {len(rows)} result(s) listed. Looking for the newest PDF-type report...")

    for position, row in enumerate(rows, start=1):
        badges = row.find_elements(By.XPATH, TYPE_BADGE_XPATH)
        badge_src = (badges[0].get_attribute("src") or "").lower() if badges else ""

        if PDF_BADGE_MARKER not in badge_src:
            print(f"[*] Skipping result #{position} (not a PDF): '{_report_name(row)}'")
            continue

        buttons = row.find_elements(By.XPATH, DOWNLOAD_BUTTON_XPATH)
        if not buttons:
            print(f"[*] Skipping result #{position} (PDF, but no download button).")
            continue

        print(f"[+] PDF report selected: result #{position} '{_report_name(row)}'")
        return buttons[0]

    # Distinct from the "clicked download but no file appeared" error raised
    # later, so the logs separate "wrong file type in results" from "the
    # download never completed".
    raise FileNotFoundError(
        f"No PDF-type report found in IG-EPN results for {volcano_name} "
        f"in {current_year} (scanned {len(rows)} most recent result(s); "
        f"all were non-PDF, e.g. PNG infographics)."
    )


def archive_previous_downloads():
    """
    Moves every previously downloaded PDF out of DATA_DIR and into DATA_DIR/_archive.

    This is what makes "newest file in DATA_DIR" a trustworthy signal: with the
    directory cleared beforehand, any PDF present after the download step is
    necessarily the file this run just downloaded, never a leftover belonging to
    a different volcano. Archived names are prefixed with a timestamp because
    Chrome reuses the same download name once the directory is empty, so plain
    basenames would overwrite each other run after run.
    """
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for f in glob.glob(os.path.join(DATA_DIR, "*.pdf")):
        name = os.path.basename(f)
        if name == FALLBACK_NAME:
            continue
        shutil.move(f, os.path.join(ARCHIVE_DIR, f"{stamp}_{name}"))
        print(f"[*] Archived previous download: '{name}'")


def get_latest_bulletin(volcano_name):
    """
    Retrieves the latest bulletin for a given volcano from the IGEPN website.
    Uses a headless browser to navigate the form, handle iframes, and download 
    the PDF file into the local data directory.
    """
    url = "https://www.igepn.edu.ec/servicios/busqueda-informes"

    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

    # Clear leftovers BEFORE the download flow starts. Done outside the try block
    # on purpose: if archiving fails we want a hard error, not a silent slide into
    # the fallback while stale PDFs are still sitting in DATA_DIR.
    archive_previous_downloads()

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
        # Wait for the results list to be interactive, then pick the newest
        # PDF-type row instead of blindly taking the first button on the page:
        # the list interleaves PDF reports with PNG infographics.
        print("[*] Search completed. Looking for the download button...")
        wait.until(EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'Descargar Informe')]")))
        download_button = find_first_pdf_download_button(driver, volcano_name, current_year)
        driver.execute_script("arguments[0].scrollIntoView({behavior: 'auto', block: 'center'});", download_button)
        time.sleep(1)
        download_button.click()
        
        print("[*] Download button clicked. Waiting for the file to reach the disk...")
        time.sleep(5)

        # --- STEP 6: File validation ---
        # DATA_DIR was emptied of downloads above, so anything matched here was
        # downloaded by this run. The bundled fallback is excluded because it is
        # always present and would otherwise masquerade as a fresh download.
        pdf_files = [
            f for f in glob.glob(os.path.join(DATA_DIR, "*.pdf"))
            if os.path.basename(f) != FALLBACK_NAME
        ]
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
    fallback_path = os.path.join(DATA_DIR, FALLBACK_NAME)
    return fallback_path, FALLBACK_NAME, f"Local Fallback ({FALLBACK_NAME})"
