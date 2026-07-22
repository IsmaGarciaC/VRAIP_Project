import sqlite3
import os

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
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            bulletin_id   INTEGER NOT NULL,
            alert_level   TEXT    NOT NULL,
            activity_type TEXT,
            emissions_flag INTEGER DEFAULT 0,
            classified_at TEXT DEFAULT CURRENT_TIMESTAMP,
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

# Call the function to initialize the database
if __name__ == "__main__":
    init_db()
