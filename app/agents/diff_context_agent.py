from typing import Dict, Any, List
from backend.app.tools.git_tool import GitTool, ChangedFile
from backend.app.core.config import config

class DiffContextAgent:
    """Analyzes Git diff, identifies changed files, extracts affected code hunks, and computes diff hash."""

    @classmethod
    def execute(cls, raw_diff: str) -> Dict[str, Any]:
        if not raw_diff or not raw_diff.strip():
            # Try to read local Git repository diff if empty
            local_diff = GitTool.get_local_git_diff()
            if local_diff:
                raw_diff = local_diff

        if not raw_diff or not raw_diff.strip():
            return {
                "diff_hash": "",
                "changed_files": [],
                "file_count": 0,
                "total_added_lines": 0,
                "has_diff": False,
                "summary": "No git changes detected."
            }

        diff_hash = GitTool.calculate_diff_hash(raw_diff)
        changed_files: List[ChangedFile] = GitTool.parse_diff(raw_diff)

        # Apply guardrail line limits if needed
        total_added = sum(len(f.added_lines) for f in changed_files)
        
        file_summaries = []
        for f in changed_files:
            file_summaries.append({
                "file": f.new_path or f.old_path,
                "status": f.status,
                "added_lines_count": len(f.added_lines),
                "hunk_count": len(f.hunks)
            })

        return {
            "diff_hash": diff_hash,
            "changed_files": changed_files,
            "file_summaries": file_summaries,
            "file_count": len(changed_files),
            "total_added_lines": total_added,
            "has_diff": True,
            "raw_diff": raw_diff
        }
