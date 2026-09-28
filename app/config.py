import os
from dotenv import load_dotenv

load_dotenv()

HINDSIGHT_BASE_URL = os.getenv("HINDSIGHT_BASE_URL", "http://localhost:8080")
HINDSIGHT_API_KEY = os.getenv("HINDSIGHT_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
HINDSIGHT_BANK_ID = os.getenv("HINDSIGHT_BANK_ID", "acme-platform-team")

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
PRIMARY_MODEL = "openai/gpt-oss-120b"
FALLBACK_MODEL = "qwen/qwen3-32b"
