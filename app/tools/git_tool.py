import hashlib
import re
import subprocess
from typing import List, Dict, Any, Optional

class GitDiffHunk:
    def __init__(self, old_start: int, old_count: int, new_start: int, new_count: int, lines: List[str]):
        self.old_start = old_start
        self.old_count = old_count
        self.new_start = new_start
        self.new_count = new_count
        self.lines = lines

class ChangedFile:
    def __init__(self, old_path: str, new_path: str, status: str, hunks: List[GitDiffHunk], raw_patch: str):
        self.old_path = old_path
        self.new_path = new_path
        self.status = status # MODIFIED, ADDED, DELETED
        self.hunks = hunks
        self.raw_patch = raw_patch
        self.added_lines: List[Dict[str, Any]] = [] # [{"line_no": int, "content": str}]

class GitTool:
    """Read-only Git utility for parsing diffs, identifying modified hunks, and generating diff hashes."""

    @staticmethod
    def calculate_diff_hash(diff_text: str) -> str:
        """Calculates a deterministic SHA256 hash of the git diff."""
        cleaned = diff_text.strip().encode("utf-8")
        return hashlib.sha256(cleaned).hexdigest()

    @staticmethod
    def parse_diff(raw_diff: str) -> List[ChangedFile]:
        """Parses a unified git diff into structured ChangedFile objects with line mapping."""
        if not raw_diff or not raw_diff.strip():
            return []

        files: List[ChangedFile] = []
        file_blocks = re.split(r"(?=^diff --git )", raw_diff, flags=re.MULTILINE)

        for block in file_blocks:
            if not block.strip():
                continue

            lines = block.splitlines()
            old_path = ""
            new_path = ""
            status = "MODIFIED"

            # Parse headers
            for line in lines[:10]:
                if line.startswith("--- a/"):
                    old_path = line[6:]
                elif line.startswith("--- /dev/null"):
                    old_path = ""
                    status = "ADDED"
                elif line.startswith("+++ b/"):
                    new_path = line[6:]
                elif line.startswith("+++ /dev/null"):
                    new_path = ""
                    status = "DELETED"
                elif line.startswith("diff --git"):
                    parts = line.split(" ")
                    if len(parts) >= 4:
                        if not old_path and parts[2].startswith("a/"):
                            old_path = parts[2][2:]
                        if not new_path and parts[3].startswith("b/"):
                            new_path = parts[3][2:]

            target_path = new_path or old_path or "unknown_file"
            hunks: List[GitDiffHunk] = []
            current_hunk_lines: List[str] = []
            hunk_header_match = None
            added_lines: List[Dict[str, Any]] = []

            hunk_regex = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
            current_new_line = 0

            for line in lines:
                hunk_match = hunk_regex.match(line)
                if hunk_match:
                    if hunk_header_match and current_hunk_lines:
                        # save previous hunk
                        hunks.append(GitDiffHunk(
                            int(hunk_header_match.group(1)),
                            int(hunk_header_match.group(2) or 1),
                            int(hunk_header_match.group(3)),
                            int(hunk_header_match.group(4) or 1),
                            current_hunk_lines
                        ))
                        current_hunk_lines = []
                    hunk_header_match = hunk_match
                    current_new_line = int(hunk_match.group(3))
                    continue

                if hunk_header_match is not None:
                    current_hunk_lines.append(line)
                    if line.startswith("+") and not line.startswith("+++"):
                        added_lines.append({
                            "line_no": current_new_line,
                            "content": line[1:]
                        })
                        current_new_line += 1
                    elif line.startswith("-") and not line.startswith("---"):
                        pass # removed line
                    else:
                        current_new_line += 1

            if hunk_header_match and current_hunk_lines:
                hunks.append(GitDiffHunk(
                    int(hunk_header_match.group(1)),
                    int(hunk_header_match.group(2) or 1),
                    int(hunk_header_match.group(3)),
                    int(hunk_header_match.group(4) or 1),
                    current_hunk_lines
                ))

            changed_file = ChangedFile(old_path, new_path or target_path, status, hunks, block)
            changed_file.added_lines = added_lines
            files.append(changed_file)

        return files

    @staticmethod
    def get_local_git_diff(repo_dir: str = ".") -> Optional[str]:
        """Read-only extraction of working tree diff from a local Git repository."""
        try:
            # Check staged and unstaged diff
            diff_proc = subprocess.run(
                ["git", "diff", "HEAD"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=5,
                check=False
            )
            if diff_proc.returncode == 0 and diff_proc.stdout.strip():
                return diff_proc.stdout
            
            # Try plain git diff
            diff_proc2 = subprocess.run(
                ["git", "diff"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=5,
                check=False
            )
            if diff_proc2.returncode == 0 and diff_proc2.stdout.strip():
                return diff_proc2.stdout
            return ""
        except Exception:
            return None
