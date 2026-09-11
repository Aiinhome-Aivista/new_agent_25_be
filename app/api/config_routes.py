from flask import Blueprint, request, jsonify
from app.core.config import config

config_bp = Blueprint("config", __name__, url_prefix="/api/v1/config")

@config_bp.route("", methods=["GET"])
def get_config():
    """Returns active runtime configuration and health metrics."""
    return jsonify({
        "mode": config.MODE,
        "gemini_model": config.GEMINI_MODEL,
        "mistral_model": config.MODEL_NAME,
        "mistral_local_url": config.MISTRAL_LOCAL_URL,
        "mistral_local_model": config.MISTRAL_LOCAL_MODEL,
        "mysql_host": config.MYSQL_HOST,
        "mysql_port": config.MYSQL_PORT,
        "mysql_database": config.MYSQL_DATABASE,
        "mysql_user": config.MYSQL_USER,
        "is_sqlite_fallback": False,
        "strict_gatekeeper": config.STRICT_GATEKEEPER,
        "redact_secrets": config.REDACT_SECRETS
    }), 200

@config_bp.route("", methods=["POST"])
def update_config():
    """Dynamically update LLM Mode or parameters."""
    data = request.get_json() or {}
    if "mode" in data:
        config.MODE = data["mode"]
    if "gemini_model" in data:
        config.GEMINI_MODEL = data["gemini_model"]
    if "mistral_local_url" in data:
        config.MISTRAL_LOCAL_URL = data["mistral_local_url"]
    if "strict_gatekeeper" in data:
        config.STRICT_GATEKEEPER = bool(data["strict_gatekeeper"])
    
    return jsonify({
        "message": "Configuration updated successfully",
        "current_mode": config.MODE
    }), 200
