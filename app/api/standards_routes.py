from flask import Blueprint, request, jsonify
from app.rag.standards_store import standards_store
from app.core.database import SessionLocal
from app.models.entities import CodingStandard
from app.core.logging_config import logger

standards_bp = Blueprint("standards", __name__, url_prefix="/api/v1/standards")

@standards_bp.route("", methods=["GET"])
def get_standards():
    """List all available enterprise coding standards."""
    language = request.args.get("language", "java")
    framework = request.args.get("framework", "spring-boot")
    standards = standards_store.search_relevant_standards(language=language, framework=framework)
    return jsonify({"standards": standards}), 200

@standards_bp.route("", methods=["POST"])
def add_standard():
    """Ingest a new coding standard into the knowledge catalog."""
    data = request.get_json() or {}
    rule_code = data.get("rule_code")
    title = data.get("title")
    description = data.get("description")
    
    if not rule_code or not title or not description:
        return jsonify({"error": "rule_code, title, and description are required"}), 400

    standard = {
        "rule_code": rule_code,
        "language": data.get("language", "java"),
        "framework": data.get("framework", "spring-boot"),
        "category": data.get("category", "quality"),
        "title": title,
        "description": description,
        "bad_example": data.get("bad_example", ""),
        "good_example": data.get("good_example", ""),
        "severity": data.get("severity", "WARNING"),
        "is_blocking": data.get("is_blocking", False),
        "version": data.get("version", "1.0.0")
    }
    standards_store.add_standard(standard)

    # Persist in DB
    if SessionLocal:
        try:
            db = SessionLocal()
            entity = CodingStandard(**standard)
            db.merge(entity)
            db.commit()
            db.close()
        except Exception as e:
            logger.warning(f"Could not persist standard to DB: {e}")

    return jsonify({"message": "Standard added successfully", "standard": standard}), 201
