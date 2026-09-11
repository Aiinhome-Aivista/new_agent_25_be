from flask import Blueprint, request, jsonify
from app.rag.standards_store import standards_store
from app.core import database
from app.models.entities import CodingStandard
from app.core.logging_config import logger

standards_bp = Blueprint("standards", __name__, url_prefix="/api/v1/standards")

@standards_bp.route("", methods=["GET"])
def get_standards():
    """List all available enterprise coding standards."""
    language = request.args.get("language", "java")
    framework = request.args.get("framework", "spring-boot")
    # For general RAG search with query
    query = request.args.get("query", "")
    standards = standards_store.search_relevant_standards(language=language, framework=framework, query=query)
    return jsonify({"standards": standards}), 200

@standards_bp.route("/all", methods=["GET"])
def get_all_standards():
    """List all standards for the frontend Knowledge Base UI."""
    if database.SessionLocal:
        try:
            db = database.SessionLocal()
            db_standards = db.query(CodingStandard).order_by(CodingStandard.created_at.desc()).all()
            result = [s.to_dict() for s in db_standards]
            db.close()
            return jsonify({"standards": result}), 200
        except Exception as e:
            logger.error(f"Error fetching standards from MySQL: {e}")

    # Fallback to ChromaDB
    standards = standards_store.get_all_standards()
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
    if database.SessionLocal:
        try:
            db = database.SessionLocal()
            entity = CodingStandard(**standard)
            db.merge(entity)
            db.commit()
            db.close()
        except Exception as e:
            logger.warning(f"Could not persist standard to DB: {e}")

    return jsonify({"message": "Standard added successfully", "standard": standard}), 201

@standards_bp.route("/bulk", methods=["POST"])
def add_standards_bulk():
    """Ingest multiple coding standards (JSON array)."""
    data = request.get_json()
    if not isinstance(data, list):
        return jsonify({"error": "Expected a JSON array of rules"}), 400

    added = 0
    for item in data:
        rule_code = item.get("rule_code")
        title = item.get("title")
        description = item.get("description")
        if not rule_code or not title or not description:
            continue
        
        standard = {
            "rule_code": rule_code,
            "language": item.get("language", "java"),
            "framework": item.get("framework", "spring-boot"),
            "category": item.get("category", "quality"),
            "title": title,
            "description": description,
            "bad_example": item.get("bad_example", ""),
            "good_example": item.get("good_example", ""),
            "severity": item.get("severity", "WARNING"),
            "is_blocking": item.get("is_blocking", False),
            "version": item.get("version", "1.0.0")
        }
        standards_store.add_standard(standard)
        added += 1

        # Persist in DB
        if database.SessionLocal:
            try:
                db = database.SessionLocal()
                entity = CodingStandard(**standard)
                db.merge(entity)
                db.commit()
                db.close()
            except Exception as e:
                logger.warning(f"Could not persist standard to DB: {e}")

    return jsonify({"message": f"Successfully added {added} standards"}), 201

@standards_bp.route("/<rule_code>", methods=["DELETE"])
def delete_standard(rule_code):
    """Delete a coding standard by rule_code."""
    success = standards_store.delete_standard(rule_code)
    if success:
        return jsonify({"message": f"Standard {rule_code} deleted successfully"}), 200
    return jsonify({"error": f"Failed to delete standard {rule_code}"}), 400
