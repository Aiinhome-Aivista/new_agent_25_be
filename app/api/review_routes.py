from flask import Blueprint, request, jsonify
from backend.app.agents.orchestrator import ReviewOrchestrator
from backend.app.core.database import SessionLocal
from backend.app.models.entities import ReviewSession, ReviewFinding, MissingTest, PassedCheck, AcceptanceCriteriaCheck, ReviewAuditLog
from backend.app.core.logging_config import logger

review_bp = Blueprint("reviews", __name__, url_prefix="/api/v1/reviews")

@review_bp.route("", methods=["POST"])
def create_review():
    """Trigger a full Pre-Push Code Review."""
    try:
        data = request.get_json() or {}
        git_diff = data.get("git_diff", "")
        acceptance_criteria = data.get("acceptance_criteria", "")
        repository_name = data.get("repository_name", "workspace")
        branch = data.get("branch", "main")
        language = data.get("language", "java")
        framework = data.get("framework", "spring-boot")
        author = data.get("author", "developer")

        result = ReviewOrchestrator.run_review(
            git_diff=git_diff,
            acceptance_criteria=acceptance_criteria,
            repository_name=repository_name,
            branch=branch,
            language=language,
            framework=framework,
            author=author
        )
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Error executing review: {e}", exc_info=True)
        return jsonify({"error": str(e), "status": "FAILED"}), 500

@review_bp.route("", methods=["GET"])
def list_reviews():
    """List recent review sessions from database."""
    try:
        limit = int(request.args.get("limit", 20))
        if SessionLocal:
            db = SessionLocal()
            sessions = db.query(ReviewSession).order_by(ReviewSession.created_at.desc()).limit(limit).all()
            result = [s.to_dict() for s in sessions]
            db.close()
            return jsonify({"sessions": result}), 200
        return jsonify({"sessions": []}), 200
    except Exception as e:
        logger.error(f"Error querying reviews: {e}")
        return jsonify({"error": str(e)}), 500

@review_bp.route("/<session_id>", methods=["GET"])
def get_review(session_id: str):
    """Retrieve full details of a specific review session."""
    try:
        if SessionLocal:
            db = SessionLocal()
            session = db.query(ReviewSession).filter(ReviewSession.id == session_id).first()
            if not session:
                db.close()
                return jsonify({"error": "Review session not found"}), 404

            findings = db.query(ReviewFinding).filter(ReviewFinding.session_id == session_id).all()
            missing_tests = db.query(MissingTest).filter(MissingTest.session_id == session_id).all()
            passed_checks = db.query(PassedCheck).filter(PassedCheck.session_id == session_id).all()
            ac_checks = db.query(AcceptanceCriteriaCheck).filter(AcceptanceCriteriaCheck.session_id == session_id).all()
            audit_logs = db.query(ReviewAuditLog).filter(ReviewAuditLog.session_id == session_id).order_by(ReviewAuditLog.created_at.asc()).all()

            response = {
                "session": session.to_dict(),
                "summary": session.summary,
                "pushReadiness": session.push_readiness,
                "riskLevel": session.risk_level,
                "blockingIssues": session.blocking_issues_count,
                "warningIssues": session.warning_issues_count,
                "passedChecksCount": session.passed_checks_count,
                "missingTestsCount": session.missing_tests_count,
                "issues": [f.to_dict() for f in findings],
                "missingTests": [mt.to_dict() for mt in missing_tests],
                "passedChecks": [pc.to_dict() for pc in passed_checks],
                "acceptanceCriteriaResults": [ac.to_dict() for ac in ac_checks],
                "auditLogs": [al.to_dict() for al in audit_logs],
                "reviewMetadata": {
                    "sessionId": session.id,
                    "diffHash": session.diff_hash,
                    "model": session.model_used,
                    "promptVersion": session.prompt_version,
                    "standardsVersion": session.standards_version,
                    "durationMs": session.duration_ms,
                    "timestamp": session.created_at.isoformat() if session.created_at else None
                }
            }
            db.close()
            return jsonify(response), 200
        return jsonify({"error": "Database not initialized"}), 500
    except Exception as e:
        logger.error(f"Error fetching review {session_id}: {e}")
        return jsonify({"error": str(e)}), 500
