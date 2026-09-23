import re
from typing import Dict, Any, List, Optional
from app.rag.codebase_store import codebase_store
from app.tools.git_tool import ChangedFile
from app.core.logging_config import logger


class DuplicateCodeAgent:
    """
    Push ??? ???? code-?? ??????? chunk codebase-? similarity search ???
    duplicate code detect ???? 80% similarity ??? duplicate flag ????
    """

    # 80% threshold -- user-approved
    SIMILARITY_THRESHOLD = 0.80

    # Minimum lines in a chunk for duplicate check (??? ??? snippets false positive ????)
    MIN_CHUNK_LINES = 5

    @classmethod
    def execute(
        cls,
        changed_files: List[ChangedFile],
        language: str = "python"
    ) -> Dict[str, Any]:
        """
        Changed files-?? added code ???? duplicate check ????
        Returns: { duplicates: [...], has_duplicates: bool, checked_chunks: int }
        """
        duplicates = []
        checked_chunks = 0

        # Index available ?? ?? check
        status = codebase_store.get_status()
        if not status.get("available") or status.get("indexed_files", 0) == 0:
            logger.info("DuplicateCodeAgent: Codebase not indexed, skipping duplicate check.")
            return {
                "duplicates": [],
                "has_duplicates": False,
                "checked_chunks": 0,
                "skipped": True,
                "skip_reason": "Codebase not indexed. Index workspace first."
            }

        for changed_file in changed_files:
            file_path = changed_file.new_path or changed_file.old_path or ""
            if not file_path:
                continue

            # Added lines ???? meaningful chunks ??? ???
            added_code = cls._extract_added_code(changed_file)
            if not added_code:
                continue

            # Code-?? chunk ???
            chunks = cls._chunk_added_code(added_code)

            for chunk_text, base_line in chunks:
                if len(chunk_text.strip().splitlines()) < cls.MIN_CHUNK_LINES:
                    continue  # ??? snippets skip

                checked_chunks += 1

                # Codebase-? similar code ?????
                similar_results = codebase_store.search_similar_code(
                    query_code=chunk_text,
                    language=language,
                    n_results=3,
                    exclude_file=file_path  # ????? file-?? match skip
                )

                for match in similar_results:
                    if match["similarity"] >= cls.SIMILARITY_THRESHOLD:
                        sim_pct = int(match["similarity"] * 100)
                        duplicates.append({
                            "file": file_path,
                            "line": base_line,
                            "end_line": base_line + len(chunk_text.splitlines()) - 1,
                            "severity": "WARNING",
                            "category": "Code Duplication",
                            "rule_id": "QUAL-DUP-001",
                            "message": (
                                f"?? code-?? {sim_pct}% duplicate ?????? ???? "
                                f"'{match['file_path']}' ? (Line {match['start_line']}-{match['end_line']})?"
                            ),
                            "suggestion": (
                                f"Duplicate avoid ????? "
                                f"'{match['file_path']}:{match['start_line']}' ???? existing code reuse ????? "
                                f"DRY (Don't Repeat Yourself) principle follow ?????"
                            ),
                            "evidence": f"Similarity: {sim_pct}% with {match['file_path']}:{match['start_line']}-{match['end_line']}",
                            "duplicate_in_file": match["file_path"],
                            "duplicate_at_line": match["start_line"],
                            "similarity_score": match["similarity"],
                            "is_blocking": False,
                            "source_tool": "duplicate_code_agent",
                            "fix_code": ""
                        })
                        break  # ??????? chunk-?? ???? ??????? similar ????? report

        logger.info(
            f"DuplicateCodeAgent: checked {checked_chunks} chunks, "
            f"found {len(duplicates)} duplicates."
        )

        return {
            "duplicates": duplicates,
            "has_duplicates": len(duplicates) > 0,
            "checked_chunks": checked_chunks,
            "skipped": False
        }

    @classmethod
    def _extract_added_code(cls, changed_file: ChangedFile) -> str:
        """Changed file-?? ???? added lines ??? ????"""
        if not changed_file.hunks:
            return ""

        added_lines = []
        for hunk in changed_file.hunks:
            for line in hunk.lines:
                # '+' ????? ???? ????? lines = added
                if hasattr(line, 'line_type') and line.line_type == '+':
                    added_lines.append(line.value if hasattr(line, 'value') else str(line))
                elif isinstance(line, str) and line.startswith('+') and not line.startswith('+++'):
                    added_lines.append(line[1:])  # '+' strip ???

        return '\n'.join(added_lines)

    @classmethod
    def _chunk_added_code(cls, code: str, chunk_size: int = 30) -> List[tuple]:
        """
        Added code-?? chunks-? ??? ????
        Returns: List of (chunk_text, approximate_start_line)
        """
        lines = code.split('\n')
        chunks = []
        i = 0
        while i < len(lines):
            end = min(i + chunk_size, len(lines))
            chunk = '\n'.join(lines[i:end]).strip()
            if chunk:
                chunks.append((chunk, i + 1))
            i += chunk_size - 3  # 3 lines overlap
        return chunks
