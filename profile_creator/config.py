import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(BASE_DIR, "fonts")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")

os.makedirs(REPORTS_DIR, exist_ok=True)
os.makedirs(FONTS_DIR, exist_ok=True)