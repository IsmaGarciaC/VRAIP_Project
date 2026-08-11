import sqlite3
import os
import pandas as pd

# Define the path to the database file.
# VRAIP_DB_PATH overrides it so verification runs can be pointed at a throwaway
# copy instead of writing into the live database.
DB_PATH = os.getenv(
    "VRAIP_DB_PATH",
    os.path.join(os.path.dirname(__file__), "..", "data", "vraip.db"),
)

# Define some sample volcano data
VOLCANOES = [
    ("Cotopaxi",   -0.6773, -78.4367, "COT"),
    ("Tungurahua", -1.4679, -78.4427, "TUN"),
    ("Reventador", -0.0777, -77.6564, "REV"),
    ("Sangay",     -2.0051, -78.3417, "SAN"),
]

# Function to get a database connection
def get_connection():
    return sqlite3.connect(DB_PATH)

# Function to initialize the database
def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # Create the tables if they don't exist
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS volcanoes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            latitude    REAL    NOT NULL,
            longitude   REAL    NOT NULL,
            igepn_code  TEXT
        );

        CREATE TABLE IF NOT EXISTS bulletins (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            volcano_id   INTEGER NOT NULL,
            published_at TEXT,
            source_url   TEXT,
            raw_text     TEXT,
            pdf_filename TEXT,
            created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (volcano_id) REFERENCES volcanoes(id)
        );

        CREATE TABLE IF NOT EXISTS classifications (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            bulletin_id           INTEGER NOT NULL,
            alert_level           TEXT NOT NULL,
            alert_level_detected  INTEGER NOT NULL DEFAULT 1,
            surface_activity      TEXT,
            internal_activity     TEXT,
            ash_emissions         INTEGER DEFAULT 0,
            gas_emissions         INTEGER DEFAULT 0,
            incandescence         INTEGER DEFAULT 0,
            lahars_detected       INTEGER DEFAULT 0,
            explosions_count      INTEGER DEFAULT 0,
            max_column_height_m   INTEGER DEFAULT 0,
            classified_at         TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (bulletin_id) REFERENCES bulletins(id)
        );

        CREATE TABLE IF NOT EXISTS ai_alerts (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            classification_id INTEGER NOT NULL,
            explanation       TEXT,
            recommendations   TEXT,
            generated_at      TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (classification_id) REFERENCES classifications(id)
        );
    """)

    # Migrate pre-existing classifications tables that predate the
    # alert_level_detected column (CREATE TABLE IF NOT EXISTS won't add it).
    cursor.execute("PRAGMA table_info(classifications)")
    existing_columns = [row[1] for row in cursor.fetchall()]
    if "alert_level_detected" not in existing_columns:
        cursor.execute(
            "ALTER TABLE classifications ADD COLUMN alert_level_detected INTEGER NOT NULL DEFAULT 1"
        )

    # Seed volcanoes only if the database is empty
    cursor.execute("SELECT count(*) FROM volcanoes")
    if cursor.fetchone()[0] == 0:
        cursor.executemany(
            "INSERT INTO volcanoes (name,latitude, longitude, igepn_code) VALUES (?, ?, ?, ?)",
            VOLCANOES
        )
        print("Volcanoes inserted successfully.")

    # Commit the changes and close the connection
    conn.commit()
    conn.close()
    print("Database initialized successfully.")

# Read-only helper for the future Chapter 5 dashboard.
# Not called anywhere in the current pipeline (scraper/ingestion/classifier/interpreter).
def get_bulletins_dataframe():
    conn = get_connection()
    query = """
        SELECT
            v.name AS volcano_name,
            b.published_at,
            c.alert_level
        FROM bulletins b
        JOIN volcanoes v ON b.volcano_id = v.id
        LEFT JOIN classifications c ON c.bulletin_id = b.id
        ORDER BY b.published_at DESC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

# Read-only helper backing the Streamlit dashboard (app.py).
# Returns one row per bulletin with its volcano, classification and AI alert
# joined in. Never writes.
def get_dashboard_dataframe():
    """Full pipeline join for the dashboard: volcanoes -> bulletins -> classifications -> ai_alerts.

    Exactly one row per bulletin: where a bulletin has several classifications, or a
    classification several ai_alerts (re-runs of the pipeline), only the most recent
    row of each is joined. Volcanoes with no ingested bulletins do not appear here --
    use get_volcanoes_dataframe() for the complete monitored list.

    Note: published_at is the INGESTION timestamp, not the bulletin's stated
    publication date, and source_url is the portal entry point rather than a
    document-specific permalink.
    """
    conn = get_connection()
    query = """
        SELECT
            v.id           AS volcano_id,
            v.name         AS volcano_name,
            v.latitude     AS latitude,
            v.longitude    AS longitude,
            v.igepn_code   AS igepn_code,
            b.id           AS bulletin_id,
            b.published_at AS published_at,
            b.source_url   AS source_url,
            b.pdf_filename AS pdf_filename,
            c.alert_level          AS alert_level,
            c.alert_level_detected AS alert_level_detected,
            c.surface_activity     AS surface_activity,
            c.internal_activity    AS internal_activity,
            c.ash_emissions        AS ash_emissions,
            c.gas_emissions        AS gas_emissions,
            c.incandescence        AS incandescence,
            c.lahars_detected      AS lahars_detected,
            c.explosions_count     AS explosions_count,
            c.max_column_height_m  AS max_column_height_m,
            a.explanation     AS explanation,
            a.recommendations AS recommendations,
            a.generated_at    AS generated_at
        FROM bulletins b
        JOIN volcanoes v ON b.volcano_id = v.id
        LEFT JOIN classifications c
               ON c.id = (SELECT MAX(id) FROM classifications WHERE bulletin_id = b.id)
        LEFT JOIN ai_alerts a
               ON a.id = (SELECT MAX(id) FROM ai_alerts WHERE classification_id = c.id)
        ORDER BY b.published_at DESC, b.id DESC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

# Read-only helper backing the dashboard map: every monitored volcano, including
# those that have no successfully ingested bulletin yet.
def get_volcanoes_dataframe():
    """Returns all seeded volcanoes with their coordinates, as a DataFrame."""
    conn = get_connection()
    query = """
        SELECT id AS volcano_id, name AS volcano_name, latitude, longitude, igepn_code
        FROM volcanoes
        ORDER BY id
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

# Read-only helper used by main.py to orchestrate the pipeline over every
# seeded volcano in a single invocation.
def get_all_volcanoes():
    """Returns list of (id, name) tuples for all seeded volcanoes."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM volcanoes ORDER BY id")
    result = cursor.fetchall()
    conn.close()
    return result

# Call the function to initialize the database
if __name__ == "__main__":
    init_db()
