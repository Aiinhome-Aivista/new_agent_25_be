from flask import Blueprint, request, jsonify
from app.rag.codebase_store import codebase_store
from app.core.logging_config import logger

codebase_bp = Blueprint("codebase", __name__, url_prefix="/api/v1/codebase")


@codebase_bp.route("/index", methods=["POST"])
def index_files():
    """
    VS Code Extension ???? workspace files batch-? ???????
    Body: { "files": [{ "path": "...", "content": "...", "language": "..." }] }
    """
    try:
        data = request.get_json(force=True)
        if not data or "files" not in data:
            return jsonify({"error": "Missing 'files' in request body"}), 400

        files = data["files"]
        if not isinstance(files, list):
            return jsonify({"error": "'files' must be a list"}), 400

        total_chunks = 0
        indexed_files = 0
        skipped_files = 0
        errors = []

        for file_info in files:
            file_path = file_info.get("path", "")
            content = file_info.get("content", "")
            language = file_info.get("language")

            if not file_path or not content:
                skipped_files += 1
                continue

            # Exclude patterns check
            if codebase_store.should_exclude(file_path):
                skipped_files += 1
                continue

            try:
                chunk_count = codebase_store.index_file(file_path, content, language)
                total_chunks += chunk_count
                indexed_files += 1
            except Exception as e:
                errors.append({"file": file_path, "error": str(e)})
                logger.error(f"Error indexing file {file_path}: {e}")

        return jsonify({
            "success": True,
            "indexed_files": indexed_files,
            "skipped_files": skipped_files,
            "total_chunks": total_chunks,
            "errors": errors[:10]  # Max 10 errors return
        }), 200

    except Exception as e:
        logger.error(f"Error in /codebase/index: {e}")
        return jsonify({"error": str(e)}), 500


@codebase_bp.route("/status", methods=["GET"])
def get_status():
    """Codebase index-?? current status return ????"""
    try:
        status = codebase_store.get_status()
        return jsonify(status), 200
    except Exception as e:
        logger.error(f"Error in /codebase/status: {e}")
        return jsonify({"error": str(e)}), 500


@codebase_bp.route("/clear", methods=["DELETE"])
def clear_index():
    """???? codebase index clear ??? -- full re-index-?? ??? call ????"""
    try:
        codebase_store.clear_all()
        return jsonify({"success": True, "message": "Codebase index cleared."}), 200
    except Exception as e:
        logger.error(f"Error in /codebase/clear: {e}")
        return jsonify({"error": str(e)}), 500


@codebase_bp.route("/reindex-file", methods=["POST"])
def reindex_file():
    """???? single file re-index ??? -- file save ??? call ??? ?????"""
    try:
        data = request.get_json(force=True)
        file_path = data.get("path", "")
        content = data.get("content", "")
        language = data.get("language")

        if not file_path or not content:
            return jsonify({"error": "Missing 'path' or 'content'"}), 400

        chunk_count = codebase_store.index_file(file_path, content, language)
        return jsonify({
            "success": True,
            "file": file_path,
            "chunks_indexed": chunk_count
        }), 200
    except Exception as e:
        logger.error(f"Error in /codebase/reindex-file: {e}")
        return jsonify({"error": str(e)}), 500
