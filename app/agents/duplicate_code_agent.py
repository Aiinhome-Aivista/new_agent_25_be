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

            # Extract added lines with real line numbers from diff
            added_lines = cls._extract_added_lines(changed_file)
            if not added_lines:
                continue

            # Chunk added code using function boundaries + sliding window with REAL line tracking
            chunks = cls._chunk_added_lines(added_lines, language)

            for chunk_text, start_line, end_line in chunks:
                if len(chunk_text.strip().splitlines()) < cls.MIN_CHUNK_LINES:
                    continue

                checked_chunks += 1

                # Search similar code in codebase (handles both intra-file and inter-file duplicates)
                similar_results = codebase_store.search_similar_code(
                    query_code=chunk_text,
                    language=language,
                    n_results=5,
                    exclude_file=file_path,
                    exclude_line=start_line
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
                            "line": start_line,
                            "end_line": end_line,
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
        raw_lines = [l for l in chunk_text.splitlines() if l.strip()]
        is_full_method = False

        if is_same_file:
            if target_sig:
                fn_name, args, ret_type = target_sig
                if lang == "python":
                    call_stmt = f"return self.{fn_name}({args})" if "self" in chunk_text else f"return {fn_name}({args})"
                elif lang == "java" or "java" in lang:
                    has_return = ret_type and ret_type != "void"
                    prefix = "return " if has_return else ""
                    call_stmt = f"{prefix}this.{fn_name}({args});"
                else:
                    call_stmt = f"return this.{fn_name}({args});"
            else:
                if lang == "python":
                    call_stmt = "return self.get_shared_data()"
                elif lang == "java" or "java" in lang:
                    call_stmt = "return this.getSharedData();"
                else:
                    call_stmt = "return this.getSharedData();"
        else:
            base_filename = match_file.replace('\\', '/').split('/')[-1]
            class_name = base_filename.split('.')[0] if '.' in base_filename else "SharedService"
            instance_name = class_name[0].lower() + class_name[1:] if class_name else "sharedService"

            if target_sig:
                fn_name, args, ret_type = target_sig
                if lang == "python":
                    call_stmt = f"return self.{instance_name}.{fn_name}({args})" if "self" in chunk_text else f"return {instance_name}.{fn_name}({args})"
                elif lang == "java" or "java" in lang:
                    has_return = ret_type and ret_type != "void"
                    prefix = "return " if has_return else ""
                    call_stmt = f"{prefix}{instance_name}.{fn_name}({args});"
                else:
                    call_stmt = f"return {instance_name}.{fn_name}({args});"
            else:
                if lang == "python":
                    call_stmt = f"return {instance_name}.execute_logic()"
                elif lang == "java" or "java" in lang:
                    call_stmt = f"return {instance_name}.executeLogic();"
                else:
                    call_stmt = f"return {instance_name}.executeLogic();"

        # Check if the chunk represents a whole method definition so the replacement is self-contained
        if len(raw_lines) >= 2:
            first_line = raw_lines[0].strip()
            last_line = raw_lines[-1].strip()
            if (lang == "java" or "java" in lang) and ("{" in first_line or (len(raw_lines) > 1 and "{" in raw_lines[1])) and last_line == "}":
                sig_header = raw_lines[0] if "{" in raw_lines[0] else raw_lines[0] + " " + raw_lines[1]
                if "{" in sig_header:
                    sig_header = sig_header[:sig_header.find("{") + 1]
                return f"{sig_header}\n        {call_stmt}\n    }}"
            elif lang == "python" and first_line.startswith("def ") and first_line.endswith(":"):
                return f"{first_line}\n        {call_stmt}"

        return call_stmt

    @classmethod
    def _extract_added_lines(cls, changed_file: ChangedFile) -> List[Dict[str, Any]]:
        """Extract added lines with real line numbers from changed_file."""
        if hasattr(changed_file, 'added_lines') and changed_file.added_lines:
            return changed_file.added_lines

        added_lines = []
        if changed_file.hunks:
            for hunk in changed_file.hunks:
                curr_line = getattr(hunk, 'new_start', 1)
                for line in hunk.lines:
                    if hasattr(line, 'line_type') and line.line_type == '+':
                        val = line.value if hasattr(line, 'value') else str(line)
                        added_lines.append({"line_no": curr_line, "content": val})
                        curr_line += 1
                    elif isinstance(line, str) and line.startswith('+') and not line.startswith('+++'):
                        added_lines.append({"line_no": curr_line, "content": line[1:]})
                        curr_line += 1
                    elif (hasattr(line, 'line_type') and line.line_type == '-') or (isinstance(line, str) and line.startswith('-') and not line.startswith('---')):
                        pass  # deleted line in hunk doesn't advance new file line counter
                    else:
                        curr_line += 1
        return added_lines

    @classmethod
    def _chunk_added_lines(cls, added_lines: List[Dict[str, Any]], language: str = "general") -> List[Tuple[str, int, int]]:
        """
        Chunk added code by function/method boundary first, and then with a sliding window,
        preserving the EXACT real start_line and end_line in the modified file.
        Returns: List of (chunk_text, start_line, end_line)
        """
        if not added_lines:
            return []

        chunks: List[Tuple[str, int, int]] = []
        seen_texts = set()

        full_code = "\n".join(l["content"] for l in added_lines)

        # 1. Function / method boundary chunks
        try:
            fn_chunks = codebase_store._chunk_by_function_boundary(full_code, language)
            for c in fn_chunks:
                txt = c.get('text', '').strip()
                if txt and len(txt.splitlines()) >= cls.MIN_CHUNK_LINES:
                    if txt not in seen_texts:
                        seen_texts.add(txt)
                        rel_start_1based = c.get('start_line', 1)
                        rel_idx = max(0, min(len(added_lines) - 1, rel_start_1based - 1))
                        real_start_line = added_lines[rel_idx]["line_no"]
                        line_count = len(txt.splitlines())
                        end_idx = max(rel_idx, min(len(added_lines) - 1, rel_idx + line_count - 1))
                        real_end_line = added_lines[end_idx]["line_no"]
                        chunks.append((txt, real_start_line, real_end_line))
        except Exception as e:
            logger.warning(f"Failed to chunk added code by function boundary: {e}")

        # 2. Sliding window chunks (18 lines, step 14)
        chunk_size = 18
        i = 0
        while i < len(added_lines):
            end_i = min(i + chunk_size, len(added_lines))
            window_lines = added_lines[i:end_i]
            chunk_text = "\n".join(l["content"] for l in window_lines).strip()
            if chunk_text and len(chunk_text.splitlines()) >= cls.MIN_CHUNK_LINES:
                if chunk_text not in seen_texts:
                    seen_texts.add(chunk_text)
                    start_line = window_lines[0]["line_no"]
                    end_line = window_lines[-1]["line_no"]
                    chunks.append((chunk_text, start_line, end_line))
            i += max(1, chunk_size - 4)

        return chunks

