import os
from dotenv import load_dotenv
load_dotenv()

# --- API Keys ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
if GROQ_API_KEY:
    os.environ["GROQ_API_KEY"] = GROQ_API_KEY

# --- LLM Model Names (1 Main + 2 Backups) ---
CLASSIFICATION_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
]

VISION_MODELS = [
    "qwen/qwen3.6-27b",
    "qwen/qwen3.8-27b",
]

# --- Search Keywords ---
SEARCH_KEYWORDS = [
    "HVAC",
]

# --- Tender Portals ---
PORTALS = [
    {
        "name": "Kerala eTenders",
        "url": "https://etenders.kerala.gov.in/nicgep/app?page=FrontEndLatestActiveTenders&service=page",
        "type": "gepnic"
    },
    {
        "name": "CPPP eProcure",
        "url": "https://eprocure.gov.in/eprocure/app?page=FrontEndLatestActiveTenders&service=page",
        "type": "gepnic"
    },
    {
        "name": "CPPP Master Portal (Aggregator)",
        "url": "https://eprocure.gov.in/cppp/latestactivetendersnew/cpppdata",
        "type": "cppp_master"
    }
]

# --- CAPTCHA Settings ---
CAPTCHA_MAX_RETRIES = 20

# --- Pagination Limit ---
MAX_PAGES = 30

# --- Concurrency ---
BATCH_SIZE = 3

# --- Vector DB / Confidence Scoring ---
PDF_FOLDER = os.path.join(os.path.dirname(__file__), "docs")
VECTOR_DB_PATH = os.path.join(os.path.dirname(__file__), "chroma_db")
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
CHUNK_SIZE = 200
CHUNK_OVERLAP = 50
GOOD_FIT_THRESHOLD = 75
MEDIUM_FIT_THRESHOLD = 50

# --- Email Reporting ---
EMAIL_SENDER = os.getenv("EMAIL_SENDER", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
EMAIL_RECIPIENT = os.getenv("EMAIL_RECIPIENT", "ayrtonjoep@gmail.com")
