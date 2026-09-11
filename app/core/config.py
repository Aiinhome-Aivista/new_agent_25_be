import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

class Config:
    # LLM Settings
    MODE = os.getenv("MODE", "Gemini") # "Gemini" or "Mistral"
    MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
    MODEL_NAME = os.getenv("MODEL_NAME", "")
    MISTRAL_LOCAL_URL = os.getenv("MISTRAL_LOCAL_URL", "")
    MISTRAL_LOCAL_MODEL = os.getenv("MISTRAL_LOCAL_MODEL", "")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "")

    # MySQL Settings
    MYSQL_HOST = os.getenv("MYSQL_HOST", "")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
    MYSQL_USER = os.getenv("MYSQL_USER", "")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "")

    # Server Settings
    PORT = int(os.getenv("PORT", 5000))
    DEBUG = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")
    SECRET_KEY = os.getenv("SECRET_KEY", "ai-code-review-secret-key-2026")

    # Guardrails
    MAX_DIFF_LINES = int(os.getenv("MAX_DIFF_LINES", 2000))
    MAX_CONTEXT_LINES = int(os.getenv("MAX_CONTEXT_LINES", 200))
    REDACT_SECRETS = os.getenv("REDACT_SECRETS", "True").lower() in ("true", "1", "yes")
    STRICT_GATEKEEPER = os.getenv("STRICT_GATEKEEPER", "True").lower() in ("true", "1", "yes")

    @classmethod
    def get_database_uri(cls) -> str:
        import urllib.parse
        encoded_user = urllib.parse.quote_plus(cls.MYSQL_USER)
        encoded_pass = urllib.parse.quote_plus(cls.MYSQL_PASSWORD)
        # Build MySQL URI with PyMySQL
        return f"mysql+pymysql://{encoded_user}:{encoded_pass}@{cls.MYSQL_HOST}:{cls.MYSQL_PORT}/{cls.MYSQL_DATABASE}?charset=utf8mb4"

config = Config()
