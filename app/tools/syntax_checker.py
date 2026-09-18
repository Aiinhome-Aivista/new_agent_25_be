import ast
import re
from typing import List, Dict, Any
from app.tools.git_tool import ChangedFile

class SyntaxChecker:
    """Deterministic AST & Syntax Integrity Checker for Python."""

    @classmethod
    def check_changed_files(cls, changed_files: List[ChangedFile], language: str = "python") -> List[Dict[str, Any]]:
        findings = []
        if (language or "").lower() != "python":
            return findings

        for cf in changed_files:
            file_path = cf.new_path or cf.old_path
            if not file_path.endswith(".py"):
                continue

            for item in cf.added_lines:
                line_no = item["line_no"]
                raw_content = item["content"]
                stripped = raw_content.strip()

                if not stripped:
                    continue

                if stripped.startswith("#"):
                    # Check for Inline comment specificity (PY-DOC-003)
                    comment_text = stripped[1:].strip()
                    # Heuristic: No spaces and long string indicates gibberish
                    if len(comment_text) > 8 and " " not in comment_text:
                        findings.append({
                            "file": file_path,
                            "line": line_no,
                            "severity": "WARNING",
                            "category": "Documentation",
                            "rule_id": "PY-DOC-003",
                            "message": f"Inline comment '{stripped}' appears to be meaningless gibberish. Comments should explain the 'Why' behind the code.",
                            "suggestion": "Remove the meaningless comment or replace it with a descriptive explanation.",
                            "fix_code": "",
                            "evidence": raw_content,
                            "is_blocking": False,
                            "source_tool": "syntax_checker"
                        })
                    continue

                # Check 1: Unclosed Parentheses / Call Syntax (e.g. `app = create_app(`)
                diff_paren = stripped.count("(") - stripped.count(")")
                if diff_paren > 0 and not stripped.startswith(("@", "def ", "class ", "if ", "while ", "with ", "for ")):
                    corrected = stripped + (")" * diff_paren)
                    findings.append({
                        "file": file_path,
                        "line": line_no,
                        "severity": "CRITICAL",
                        "category": "Syntax Error",
                        "rule_id": "SYNTAX-PY-UNCLOSED-PAREN",
                        "message": f"Unclosed parenthesis in statement '{stripped}' results in a fatal Python SyntaxError.",
                        "suggestion": f"Close the parenthesis to complete the call: '{corrected}'.",
                        "fix_code": corrected,
                        "evidence": raw_content,
                        "is_blocking": True,
                        "source_tool": "syntax_checker"
                    })
                    continue

                # Check 2: Malformed main dunder (e.g. `if  __name__ == "  _main__ ":` or `if name == " main ":`)
                if stripped.startswith("if ") and ("name" in stripped and "main" in stripped):
                    normalized_cond = re.sub(r'\s+', ' ', stripped)
                    if normalized_cond != 'if __name__ == "__main__":' and normalized_cond != "if __name__ == '__main__':":
                        findings.append({
                            "file": file_path,
                            "line": line_no,
                            "severity": "CRITICAL",
                            "category": "Syntax Error",
                            "rule_id": "QUAL-PY-DUNDER-01",
                            "message": f"Malformed Python main entrypoint conditional '{stripped}'. Python requires exact double underscores 'if __name__ == \"__main__\":'.",
                            "suggestion": "Replace with standard 'if __name__ == \"__main__\":' with exact double underscores.",
                            "fix_code": 'if __name__ == "__main__":',
                            "evidence": raw_content,
                            "is_blocking": True,
                            "source_tool": "syntax_checker"
                        })
                        continue

                # Check 3: Missing Colon on Compound Statements
                if (stripped.startswith(("if ", "elif ", "else", "def ", "async def ", "class ", "for ", "async for ", "while ", "with ", "async with ", "try", "except", "finally"))
                      and not stripped.endswith(":")
                      and not stripped.endswith("\\")):
                    corrected = stripped + ":"
                    findings.append({
                        "file": file_path,
                        "line": line_no,
                        "severity": "CRITICAL",
                        "category": "Syntax Error",
                        "rule_id": "SYNTAX-PY-MISSING-COLON",
                        "message": f"Missing colon ':' at the end of '{stripped}'. Python compound statements require a trailing colon.",
                        "suggestion": f"Append a colon at the end of the line: '{corrected}'.",
                        "fix_code": corrected,
                        "evidence": raw_content,
                        "is_blocking": True,
                        "source_tool": "syntax_checker"
                    })
                    continue

                # Check 4: Orphaned except/finally without try
                if stripped.startswith(("except ", "except:", "finally:")) and "try:" not in raw_content:
                    findings.append({
                        "file": file_path,
                        "line": line_no,
                        "severity": "CRITICAL",
                        "category": "Syntax Error",
                        "rule_id": "SYNTAX-PY-ORPHAN-EXCEPT",
                        "message": f"Orphaned '{stripped}' statement found without a matching 'try:' block.",
                        "suggestion": "If this was intended as the main execution block, replace it with 'if __name__ == \"__main__\":'.",
                        "fix_code": 'if __name__ == "__main__":',
                        "evidence": raw_content,
                        "is_blocking": True,
                        "source_tool": "syntax_checker"
                    })
                    continue

                # Check 5: AST Parser for Stray Identifiers / Invalid Syntax (e.g. `hgjhgjhgkjhj`)
                to_parse = stripped
                if stripped.endswith(":"):
                    to_parse = stripped + "\n    pass"

                try:
                    tree = ast.parse(to_parse)
                    if len(tree.body) == 1 and isinstance(tree.body[0], ast.Expr):
                        val = tree.body[0].value
                        if isinstance(val, ast.Name) and val.id not in ("pass", "Ellipsis", "_"):
                            findings.append({
                                "file": file_path,
                                "line": line_no,
                                "severity": "CRITICAL",
                                "category": "Syntax Error",
                                "rule_id": "SYNTAX-PY-STRAY-IDENTIFIER",
                                "message": f"Stray invalid identifier or undefined non-executable expression '{stripped}' found outside of any assignment or call. This causes a fatal NameError / SyntaxError.",
                                "suggestion": f"Remove the invalid stray text '{stripped}' from source code.",
                                "fix_code": "",
                                "evidence": raw_content,
                                "is_blocking": True,
                                "source_tool": "syntax_checker"
                            })
                except SyntaxError as syn_err:
                    if not any(stripped.startswith(prefix) for prefix in ("def ", "async def ", "class ", "if ", "elif ", "else", "try", "except", "finally", "while ", "for ", "async for ", "with ", "async with ")):
                        findings.append({
                            "file": file_path,
                            "line": line_no,
                            "severity": "CRITICAL",
                            "category": "Syntax Error",
                            "rule_id": "SYNTAX-PY-INVALID-SYNTAX",
                            "message": f"Python SyntaxError in statement '{stripped}': {syn_err.msg}.",
                            "suggestion": f"Correct the syntax error or remove invalid statement '{stripped}'.",
                            "fix_code": "",
                            "evidence": raw_content,
                            "is_blocking": True,
                            "source_tool": "syntax_checker"
                        })

        return findings
