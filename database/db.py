import sqlite3
import os
import pandas as pd

# Define the path to the database file
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "vraip.db")

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

# Call the function to initialize the database
if __name__ == "__main__":
    init_db()
