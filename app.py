import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import create_app
from app.core.config import config
from app.core.logging_config import logger

app = create_app()

if __name__ == "__main__":
    logger.info(f"Starting AI Code Review Agent backend on port... {config.PORT}...")
    app.run(host="0.0.0.0", port=config.PORT, debug=config.DEBUG)

