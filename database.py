import sqlite3

# --- Database Connection ---
conn = sqlite3.connect("tenders.db", check_same_thread=False)
cursor = conn.cursor()

# --- Create Table with Updated Schema ---
# Includes link, source, confidence_score, fit_category, closing_date, tender_id columns
cursor.execute('''
    CREATE TABLE IF NOT EXISTS processed_tenders(
        title TEXT PRIMARY KEY,
        status TEXT,
        link TEXT,
        source TEXT,
        confidence_score REAL,
        fit_category TEXT,
        closing_date TEXT,
        tender_id TEXT,
        organisation TEXT,
        tender_value TEXT,
        reasoning TEXT,
        matched_evidence TEXT
    )
''')

# Migrate: add new columns if they don't exist (for existing DBs)
for col_def in [
    "confidence_score REAL",
    "fit_category TEXT",
    "closing_date TEXT",
    "tender_id TEXT",
    "organisation TEXT",
    "tender_value TEXT",
    "reasoning TEXT",
    "matched_evidence TEXT",
]:
    try:
        cursor.execute(f"ALTER TABLE processed_tenders ADD COLUMN {col_def}")
    except sqlite3.OperationalError:
        pass  # Column already exists

conn.commit()


# --- Helper Functions ---

def is_duplicate(title: str) -> bool:
    """Check if a tender title has already been processed."""
    cursor.execute("SELECT title FROM processed_tenders WHERE title = ?", (title,))
    return cursor.fetchone() is not None


def save_tender(title: str, status: str, link: str = "", source: str = "",
                confidence_score: float = 0.0, fit_category: str = "",
                closing_date: str = "", tender_id: str = "",
                organisation: str = "", tender_value: str = "",
                reasoning: str = "", matched_evidence: str = ""):
    """Save a processed tender to the database."""
    cursor.execute(
        """INSERT OR REPLACE INTO processed_tenders 
           (title, status, link, source, confidence_score, fit_category, closing_date, tender_id, organisation, tender_value, reasoning, matched_evidence) 
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (title, status, link, source, confidence_score, fit_category, closing_date, tender_id, organisation, tender_value, reasoning, matched_evidence)
    )
    conn.commit()

