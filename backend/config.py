from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DOCS_DIR = BASE_DIR / "documents"
OUTPUT_DIR = BASE_DIR / "output"
STORE_DIR = BASE_DIR / "store"

for folder in (DATA_DIR, DOCS_DIR, OUTPUT_DIR, STORE_DIR):
    folder.mkdir(parents=True, exist_ok=True)

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "").rstrip("/")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "")
MAX_SOURCE_CHARS = int(os.getenv("MAX_SOURCE_CHARS", "12000"))
