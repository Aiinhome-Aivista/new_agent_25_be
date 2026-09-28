import re
import difflib
from typing import Dict, Any, List, Optional, Tuple
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

                        if is_same_file:
                            message = f"Duplicate logic detected ({sim_pct}% similarity with line {match['start_line']}-{match['end_line']} in the same file)."
                            suggestion = (
                                f"Promote code reusability: Extract this repeated block into a shared private helper method "
                                f"or reusable function within this file to adhere to DRY (Don't Repeat Yourself) principles."
                            )
                        else:
                            message = f"Duplicate logic detected ({sim_pct}% similarity with '{match['file_path']}' at line {match['start_line']}-{match['end_line']})."
                            suggestion = (
                                f"Promote code reusability: Instead of duplicating this implementation, extract the shared logic "
                                f"into a reusable utility service/helper component, or import and call the existing method from "
                                f"'{match['file_path']}' (DRY principle)."
                            )

                        reusable_fix = cls._generate_reusable_fix_code(
                            chunk_text=chunk_text,
                            match=match,
                            is_same_file=is_same_file,
                            language=language,
                            file_path=file_path
                        )

                        duplicates.append({
                            "file": file_path,
                            "line": base_line,
                            "end_line": base_line + len(chunk_text.splitlines()) - 1,
                            "severity": "WARNING",
                            "category": "Code Reusability & DRY",
                            "rule_id": "QUAL-DUP-001",
                            "message": message,
                            "suggestion": suggestion,
                            "evidence": f"Similarity: {sim_pct}% with {match['file_path']}:{match['start_line']}-{match['end_line']}",
                            "duplicate_in_file": match["file_path"],
                            "duplicate_at_line": match["start_line"],
                            "similarity_score": round(effective_sim, 4),
                            "is_blocking": False,
                            "source_tool": "duplicate_code_agent",
                            "fix_code": reusable_fix
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
    def _extract_function_signature(cls, code: str, language: str = "general") -> Optional[Tuple[str, str, str]]:
        """
        Extracts (function_name, param_args, return_type) from a code snippet.
        """
        lang = (language or "general").lower()

        # Java method pattern
        if lang == "java" or "java" in lang:
            m = re.search(
                r'(?:public|protected|private|static|final|\s)*\s+([\w<>\[\],\s]+)\s+(\w+)\s*\(([^)]*)\)',
                code
            )
            if m:
                ret_type = m.group(1).strip()
                fn_name = m.group(2).strip()
                raw_params = m.group(3).strip()
                param_names = []
                if raw_params:
                    for p in raw_params.split(','):
                        tokens = p.strip().split()
                        if tokens:
                            param_names.append(tokens[-1])
                return fn_name, ", ".join(param_names), ret_type

        # Python function pattern
        elif lang == "python":
            m = re.search(r'def\s+(\w+)\s*\(([^)]*)\)', code)
            if m:
                fn_name = m.group(1).strip()
                raw_params = m.group(2).strip()
                param_names = []
                if raw_params:
                    for p in raw_params.split(','):
                        p_name = p.split(':')[0].split('=')[0].strip()
                        if p_name and p_name not in ('self', 'cls'):
                            param_names.append(p_name)
                return fn_name, ", ".join(param_names), "def"

        # JavaScript / TypeScript pattern
        elif lang in ("typescript", "javascript"):
            m = re.search(
                r'(?:async\s+)?(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?)\s*\(([^)]*)\)',
                code
            )
            if m:
                fn_name = (m.group(1) or m.group(2) or "").strip()
                raw_params = m.group(3).strip()
                param_names = []
                if raw_params:
                    for p in raw_params.split(','):
                        p_name = p.split(':')[0].split('=')[0].strip()
                        if p_name:
                            param_names.append(p_name)
                return fn_name, ", ".join(param_names), "function"

        return None

    @classmethod
    def _generate_reusable_fix_code(
        cls,
        chunk_text: str,
        match: Dict[str, Any],
        is_same_file: bool,
        language: str,
        file_path: str
    ) -> Optional[str]:
        lang = (language or "general").lower()
        match_text = match.get("text", "")
        match_file = match.get("file_path", "")

        # Try to find function signature in matching target or current chunk
        target_sig = cls._extract_function_signature(match_text, lang) or cls._extract_function_signature(chunk_text, lang)

        if is_same_file:
            if target_sig:
                fn_name, args, ret_type = target_sig
                if lang == "python":
                    return f"return self.{fn_name}({args})" if "self" in chunk_text else f"return {fn_name}({args})"
                elif lang == "java" or "java" in lang:
                    has_return = ret_type and ret_type != "void"
                    prefix = "return " if has_return else ""
                    return f"{prefix}this.{fn_name}({args});"
                else:
                    return f"return this.{fn_name}({args});"
            else:
                if lang == "python":
                    return f"return self.get_shared_data()"
                elif lang == "java" or "java" in lang:
                    return f"return this.getSharedData();"
                else:
                    return f"return this.getSharedData();"
        else:
            base_filename = match_file.replace('\\', '/').split('/')[-1]
            class_name = base_filename.split('.')[0] if '.' in base_filename else "SharedService"
            instance_name = class_name[0].lower() + class_name[1:] if class_name else "sharedService"

            if target_sig:
                fn_name, args, ret_type = target_sig
                if lang == "python":
                    return f"return {instance_name}.{fn_name}({args})"
                elif lang == "java" or "java" in lang:
                    has_return = ret_type and ret_type != "void"
                    prefix = "return " if has_return else ""
                    return f"{prefix}{instance_name}.{fn_name}({args});"
                else:
                    return f"return {instance_name}.{fn_name}({args});"
            else:
                if lang == "python":
                    return f"return {instance_name}.execute_logic()"
                elif lang == "java" or "java" in lang:
                    return f"return {instance_name}.executeLogic();"
                else:
                    return f"return {instance_name}.executeLogic();"

    @classmethod
    def _extract_added_code(cls, changed_file: ChangedFile) -> str:
        """Extract added lines from changed file hunks or added_lines list."""
        if not changed_file.hunks:
            if hasattr(changed_file, 'added_lines') and changed_file.added_lines:
                return '\n'.join([l.get('content', '') if isinstance(l, dict) else str(l) for l in changed_file.added_lines])
            return ""

        added_lines = []
        for hunk in changed_file.hunks:
            for line in hunk.lines:
                # '+' prefix check
                if hasattr(line, 'line_type') and line.line_type == '+':
                    added_lines.append(line.value if hasattr(line, 'value') else str(line))
                elif isinstance(line, str) and line.startswith('+') and not line.startswith('+++'):
                    added_lines.append(line[1:])

        if not added_lines and hasattr(changed_file, 'added_lines') and changed_file.added_lines:
            return '\n'.join([l.get('content', '') if isinstance(l, dict) else str(l) for l in changed_file.added_lines])

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
