import re
import difflib
from typing import Dict, Any, List, Optional
from app.rag.codebase_store import codebase_store
from app.tools.git_tool import ChangedFile
from app.core.logging_config import logger


class DuplicateCodeAgent:
    """
    Scans modified and added code chunks against the indexed codebase
    to detect duplicate code (intra-file and inter-file) and promote DRY principles.
    """

    # 70% threshold to reliably detect duplicate methods and snippets
    SIMILARITY_THRESHOLD = 0.70

    # Minimum lines in a chunk for duplicate check (handles 3+ line controller/service methods)
    MIN_CHUNK_LINES = 3

    @classmethod
    def execute(
        cls,
        changed_files: List[ChangedFile],
        language: str = "python"
    ) -> Dict[str, Any]:
        """
        Scan changed files for code duplication against the indexed codebase.
        Returns: { duplicates: [...], has_duplicates: bool, checked_chunks: int }
        """
        duplicates = []
        checked_chunks = 0

        # Check if codebase index is available
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

            # Extract added code from diff
            added_code = cls._extract_added_code(changed_file)
            if not added_code:
                continue

            # Chunk added code using function boundaries + sliding window
            chunks = cls._chunk_added_code(added_code, language)

            for chunk_text, base_line in chunks:
                if len(chunk_text.strip().splitlines()) < cls.MIN_CHUNK_LINES:
                    continue

                checked_chunks += 1

                # Search similar code in codebase (handles both intra-file and inter-file duplicates)
                similar_results = codebase_store.search_similar_code(
                    query_code=chunk_text,
                    language=language,
                    n_results=5,
                    exclude_file=file_path,
                    exclude_line=base_line
                )

                for match in similar_results:
                    # Calculate vector similarity + exact lexical similarity for max accuracy
                    vector_sim = match.get("similarity", 0.0)
                    text_ratio = difflib.SequenceMatcher(
                        None,
                        chunk_text.strip(),
                        match.get("text", "").strip()
                    ).ratio()
                    effective_sim = max(vector_sim, text_ratio)

                    if effective_sim >= cls.SIMILARITY_THRESHOLD:
                        sim_pct = int(effective_sim * 100)
                        norm_cur = file_path.replace('\\', '/').lstrip('/')
                        norm_match = (match['file_path'] or '').replace('\\', '/').lstrip('/')
                        is_same_file = (norm_cur == norm_match or norm_cur.endswith(norm_match) or norm_match.endswith(norm_cur))

                        location_desc = f"in the same file (Line {match['start_line']}-{match['end_line']})" if is_same_file else f"in '{match['file_path']}' (Line {match['start_line']}-{match['end_line']})"

                        duplicates.append({
                            "file": file_path,
                            "line": base_line,
                            "end_line": base_line + len(chunk_text.splitlines()) - 1,
                            "severity": "WARNING",
                            "category": "Code Duplication",
                            "rule_id": "QUAL-DUP-001",
                            "message": (
                                f"This code is {sim_pct}% duplicate of existing code {location_desc}."
                            ),
                            "suggestion": (
                                f"Avoid duplicate code by reusing existing logic from "
                                f"'{match['file_path']}:{match['start_line']}' to follow the DRY (Don't Repeat Yourself) principle."
                            ),
                            "evidence": f"Similarity: {sim_pct}% with {match['file_path']}:{match['start_line']}-{match['end_line']}",
                            "duplicate_in_file": match["file_path"],
                            "duplicate_at_line": match["start_line"],
                            "similarity_score": round(effective_sim, 4),
                            "is_blocking": False,
                            "source_tool": "duplicate_code_agent",
                            "fix_code": ""
                        })
                        break  # Report highest similarity match per chunk

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
    def _chunk_added_code(cls, code: str, language: str = "general") -> List[tuple]:
        """
        Chunk added code by function/method boundary first, and then with a sliding window
        to ensure both complete methods and multi-line snippets are checked against the codebase.
        Returns: List of (chunk_text, approximate_start_line)
        """
        chunks = []
        seen_texts = set()

        # 1. Function / method boundary chunks (Java methods, Python functions, etc.)
        try:
            fn_chunks = codebase_store._chunk_by_function_boundary(code, language)
            for c in fn_chunks:
                txt = c.get('text', '').strip()
                if txt and len(txt.splitlines()) >= cls.MIN_CHUNK_LINES:
                    if txt not in seen_texts:
                        seen_texts.add(txt)
                        chunks.append((txt, c.get('start_line', 1)))
        except Exception as e:
            logger.warning(f"Failed to chunk added code by function boundary: {e}")

        # 2. Sliding window chunks (18 lines) to catch duplicated logic blocks within methods
        lines = code.split('\n')
        chunk_size = 18
        i = 0
        while i < len(lines):
            end = min(i + chunk_size, len(lines))
            chunk = '\n'.join(lines[i:end]).strip()
            if chunk and len(chunk.splitlines()) >= cls.MIN_CHUNK_LINES:
                if chunk not in seen_texts:
                    seen_texts.add(chunk)
                    chunks.append((chunk, i + 1))
            i += max(1, chunk_size - 4)  # 4 lines overlap

        return chunks
