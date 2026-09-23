import os

content = r"""# -*- coding: utf-8 -*-
import re
import hashlib
from typing import List, Dict, Any, Optional
from app.core.vector_db import get_codebase_collection
from app.core.logging_config import logger


class CodebaseStore:
    """RAG store for workspace codebase -- stores code chunks in ChromaDB.
    Used for context-aware review and duplicate code detection.
    """

    SUPPORTED_EXTENSIONS = {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".jsx": "javascript",
        ".java": "java",
        ".go": "go",
        ".cs": "csharp",
        ".php": "php",
        ".rb": "ruby",
        ".cpp": "cpp",
        ".c": "c",
        ".h": "c",
        ".hpp": "cpp",
        ".kt": "kotlin",
        ".swift": "swift",
        ".rs": "rust",
    }

    EXCLUDE_PATTERNS = [
        r"node_modules",
        r"\.git",
        r"dist/",
        r"build/",
        r"venv/",
        r"\.venv/",
        r"__pycache__",
        r"\.pyc$",
        r"\.min\.js$",
        r"\.min\.css$",
        r"package-lock\.json$",
        r"yarn\.lock$",
        r"\.lock$",
        r"\.env",
        r"\.DS_Store",
        r"coverage/",
        r"\.next/",
        r"\.nuxt/",
        r"target/",
        r"\.gradle/",
        r"out/",
        r"bin/",
        r"obj/",
        r"\.class$",
        r"\.jar$",
        r"\.war$",
    ]

    CHUNK_MAX_LINES = 60
    CHUNK_OVERLAP_LINES = 5

    def __init__(self):
        try:
            self.collection = get_codebase_collection()
        except Exception as e:
            logger.error(f"Failed to initialize codebase ChromaDB collection: {e}")
            self.collection = None

    def should_exclude(self, file_path: str) -> bool:
        """Check if a file/directory should be excluded from indexing."""
        normalized = file_path.replace("\\\\", "/")
        return any(re.search(pattern, normalized) for pattern in self.EXCLUDE_PATTERNS)

    def detect_language(self, file_path: str) -> Optional[str]:
        """Detect language from file extension."""
        for ext, lang in self.SUPPORTED_EXTENSIONS.items():
            if file_path.endswith(ext):
                return lang
        return None

    def _chunk_by_function_boundary(self, content: str, language: str) -> List[Dict[str, Any]]:
        """Chunk code by function/class boundaries using regex patterns."""
        lines = content.split("\n")
        chunks = []

        patterns = {
            "python": [r"^(async\s+)?def\s+\w+", r"^class\s+\w+"],
            "typescript": [
                r"^\s*(export\s+)?(async\s+)?function\s+\w+",
                r"^\s*(export\s+)?(abstract\s+)?class\s+\w+",
                r"^\s*(public|private|protected|static|async).*\w+\s*\(",
                r"^\s*(const|let|var)\s+\w+\s*=\s*(async\s+)?\(",
            ],
            "javascript": [
                r"^\s*(export\s+)?(async\s+)?function\s+\w+",
                r"^\s*(export\s+)?(class\s+\w+)",
                r"^\s*(const|let|var)\s+\w+\s*=\s*(async\s+)?\(",
            ],
            "java": [
                r"^\s*(public|private|protected|static|final|abstract|synchronized).*\w+\s*\(",
                r"^\s*(public|private|protected)?\s*(abstract\s+)?class\s+\w+",
                r"^\s*(public|private|protected)?\s*interface\s+\w+",
            ],
            "go": [
                r"^func\s+(\(\w+\s+\*?\w+\)\s+)?\w+\(",
                r"^type\s+\w+\s+(struct|interface)",
            ],
            "csharp": [
                r"^\s*(public|private|protected|internal|static|virtual|override|async).*\w+\s*\(",
                r"^\s*(public|private|protected)?\s*(abstract\s+)?class\s+\w+",
            ],
        }

        lang_patterns = patterns.get(language, patterns.get("python", []))
        compiled = [re.compile(p) for p in lang_patterns]

        boundaries = [0]
        for i, line in enumerate(lines):
            if any(pat.match(line) for pat in compiled):
                if i > 0:
                    boundaries.append(i)
        boundaries.append(len(lines))

        for idx in range(len(boundaries) - 1):
            start = boundaries[idx]
            end = boundaries[idx + 1]
            chunk_lines = lines[start:end]

            if len(chunk_lines) > self.CHUNK_MAX_LINES:
                sub_chunks = self._split_large_chunk(chunk_lines, start)
                chunks.extend(sub_chunks)
            else:
                chunk_text = "\n".join(chunk_lines).strip()
                if chunk_text:
                    chunks.append({
                        "text": chunk_text,
                        "start_line": start + 1,
                        "end_line": end,
                        "chunk_type": "function_or_class"
                    })

        if not chunks:
            return self._fixed_size_chunks(lines)

        return chunks

    def _split_large_chunk(self, lines: List[str], base_start: int) -> List[Dict[str, Any]]:
        """Split a large chunk into smaller fixed-size sub-chunks."""
        sub_chunks = []
        i = 0
        while i < len(lines):
            end = min(i + self.CHUNK_MAX_LINES, len(lines))
            chunk_text = "\n".join(lines[i:end]).strip()
            if chunk_text:
                sub_chunks.append({
                    "text": chunk_text,
                    "start_line": base_start + i + 1,
                    "end_line": base_start + end,
                    "chunk_type": "block"
                })
            i += self.CHUNK_MAX_LINES - self.CHUNK_OVERLAP_LINES
        return sub_chunks

    def _fixed_size_chunks(self, lines: List[str]) -> List[Dict[str, Any]]:
        """Chunk by fixed size when no function boundaries are found."""
        chunks = []
        i = 0
        while i < len(lines):
            end = min(i + self.CHUNK_MAX_LINES, len(lines))
            chunk_text = "\n".join(lines[i:end]).strip()
            if chunk_text:
                chunks.append({
                    "text": chunk_text,
                    "start_line": i + 1,
                    "end_line": end,
                    "chunk_type": "block"
                })
            i += self.CHUNK_MAX_LINES - self.CHUNK_OVERLAP_LINES
        return chunks

    def _make_chunk_id(self, file_path: str, start_line: int) -> str:
        """Generate a unique ID for a chunk."""
        key = f"{file_path}:{start_line}"
        return hashlib.md5(key.encode()).hexdigest()

    def index_file(self, file_path: str, content: str, language: Optional[str] = None) -> int:
        """Chunk a file and upsert into ChromaDB. Returns number of chunks indexed."""
        if not self.collection:
            return 0
        if not content or not content.strip():
            return 0

        lang = language or self.detect_language(file_path) or "general"
        self.delete_file(file_path)
        chunks = self._chunk_by_function_boundary(content, lang)

        if not chunks:
            return 0

        ids, documents, metadatas = [], [], []
        for chunk in chunks:
            chunk_id = self._make_chunk_id(file_path, chunk["start_line"])
            doc_text = f"File: {file_path}\n\n{chunk[\"text\"]}"
            ids.append(chunk_id)
            documents.append(doc_text)
            metadatas.append({
                "file_path": file_path,
                "start_line": chunk["start_line"],
                "end_line": chunk["end_line"],
                "language": lang,
                "chunk_type": chunk["chunk_type"],
            })

        try:
            BATCH_SIZE = 50
            for i in range(0, len(ids), BATCH_SIZE):
                self.collection.upsert(
                    ids=ids[i:i+BATCH_SIZE],
                    documents=documents[i:i+BATCH_SIZE],
                    metadatas=metadatas[i:i+BATCH_SIZE]
                )
            logger.info(f"Indexed {len(ids)} chunks from {file_path}")
            return len(ids)
        except Exception as e:
            logger.error(f"Failed to index file {file_path}: {e}")
            return 0

    def delete_file(self, file_path: str) -> None:
        """Delete all chunks for a given file from ChromaDB."""
        if not self.collection:
            return
        try:
            results = self.collection.get(where={"file_path": file_path})
            if results and results.get("ids"):
                self.collection.delete(ids=results["ids"])
        except Exception as e:
            logger.error(f"Error deleting chunks for {file_path}: {e}")

    def clear_all(self) -> None:
        """Clear the entire codebase index."""
        if not self.collection:
            return
        try:
            all_data = self.collection.get()
            if all_data and all_data.get("ids"):
                self.collection.delete(ids=all_data["ids"])
            logger.info("Codebase index cleared.")
        except Exception as e:
            logger.error(f"Error clearing codebase index: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Return current index status."""
        if not self.collection:
            return {"indexed_chunks": 0, "indexed_files": 0, "available": False}
        try:
            total = self.collection.count()
            all_meta = self.collection.get(include=["metadatas"])
            file_paths = set()
            if all_meta and all_meta.get("metadatas"):
                for m in all_meta["metadatas"]:
                    if m and m.get("file_path"):
                        file_paths.add(m["file_path"])
            return {
                "indexed_chunks": total,
                "indexed_files": len(file_paths),
                "available": True
            }
        except Exception as e:
            logger.error(f"Error getting codebase status: {e}")
            return {"indexed_chunks": 0, "indexed_files": 0, "available": False}

    def search_similar_code(
        self,
        query_code: str,
        language: Optional[str] = None,
        n_results: int = 5,
        exclude_file: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search for similar code chunks in the codebase index."""
        if not self.collection:
            return []
        try:
            total = self.collection.count()
            if total == 0:
                return []

            where_filter: Dict[str, Any] = {}
            if language and language.lower() not in ("", "all", "general"):
                where_filter["language"] = language.lower()

            actual_n = min(n_results + 5, total)
            query_kwargs: Dict[str, Any] = {
                "query_texts": [query_code],
                "n_results": actual_n,
                "include": ["metadatas", "distances", "documents"]
            }
            if where_filter:
                query_kwargs["where"] = where_filter

            results = self.collection.query(**query_kwargs)
            matches = []
            if results and results.get("metadatas") and results["metadatas"][0]:
                for meta, dist, doc in zip(
                    results["metadatas"][0],
                    results["distances"][0],
                    results["documents"][0]
                ):
                    similarity = 1.0 - float(dist)
                    if exclude_file and meta.get("file_path") == exclude_file:
                        continue
                    matches.append({
                        "file_path": meta.get("file_path", ""),
                        "start_line": meta.get("start_line", 0),
                        "end_line": meta.get("end_line", 0),
                        "language": meta.get("language", ""),
                        "chunk_type": meta.get("chunk_type", ""),
                        "similarity": round(similarity, 4),
                        "text": doc
                    })

            matches.sort(key=lambda x: x["similarity"], reverse=True)
            return matches[:n_results]
        except Exception as e:
            logger.error(f"Error searching similar code: {e}")
            return []

    def get_context_for_diff(
        self,
        diff_text: str,
        language: Optional[str] = None,
        max_context_chars: int = 4000
    ) -> str:
        """Build relevant codebase context string for a diff -- injected into QualityAgent prompt."""
        if not diff_text or not self.collection or self.collection.count() == 0:
            return ""
        try:
            query = diff_text[:1000]
            similar = self.search_similar_code(query, language=language, n_results=5)
            if not similar:
                return ""

            context_parts = []
            total_chars = 0
            for match in similar:
                if match["similarity"] < 0.3:
                    continue
                snippet = (
                    f"# File: {match[chr(39)file_path{chr(39)}]} "
                    f"(Line {match[chr(39)start_line{chr(39)}]}-{match[chr(39)end_line{chr(39)}]}, "
                    f"Similarity: {int(match[chr(39)similarity{chr(39)}]*100)}%)\n"
                    f"{match[chr(39)text{chr(39)}][:500]}\n"
                )
                if total_chars + len(snippet) > max_context_chars:
                    break
                context_parts.append(snippet)
                total_chars += len(snippet)

            return "\n---\n".join(context_parts)
        except Exception as e:
            logger.error(f"Error getting context for diff: {e}")
            return ""


# Singleton instance
codebase_store = CodebaseStore()
"""

print("Script loaded")

