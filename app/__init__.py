import os
import sys

# Add root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from flask import Flask, jsonify
from flask_cors import CORS
from app.core.config import config
from app.core.database import init_db, is_sqlite_fallback
from app.core.logging_config import logger
from app.api.review_routes import review_bp
from app.api.standards_routes import standards_bp
from app.api.config_routes import config_bp

def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.SECRET_KEY

    # Enable CORS for VS Code Webview and React frontend
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Initialize Database
    try:
        init_db()
    except Exception as e:
        logger.error(f"Database initialization encountered an error: {e}")

    # Register Blueprints
    app.register_blueprint(review_bp)
    app.register_blueprint(standards_bp)
    app.register_blueprint(config_bp)

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({
            "status": "healthy",
            "service": "ai-code-review-agent",
            "mode": config.MODE,
            "database_fallback": is_sqlite_fallback
        }), 200

    @app.route("/ready", methods=["GET"])
    def ready():
        return jsonify({
            "status": "ready",
            "llm_mode": config.MODE,
            "port": config.PORT
        }), 200

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Resource not found"}), 404

    @app.errorhandler(500)
    def internal_error(e):
        return jsonify({"error": "Internal server error"}), 500

    return app
