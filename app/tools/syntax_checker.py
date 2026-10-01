import ast
import re
from typing import List, Dict, Any
from app.tools.git_tool import ChangedFile

class SyntaxChecker:
    """Deterministic AST & Syntax Integrity Checker for Java, Python, TypeScript, and JavaScript."""

    JAVA_KEYWORDS = {
        "abstract", "assert", "boolean", "break", "byte", "case", "catch", "char",
        "class", "const", "continue", "default", "do", "double", "else", "enum",
        "extends", "final", "finally", "float", "for", "goto", "if", "implements",
        "import", "instanceof", "int", "interface", "long", "native", "new",
        "package", "private", "protected", "public", "return", "short", "static",
        "strictfp", "super", "switch", "synchronized", "this", "throw", "throws",
        "transient", "try", "void", "volatile", "while", "record", "sealed",
        "non-sealed", "permits", "yield", "var", "true", "false", "null"
    }

    JS_TS_KEYWORDS = {
        "break", "case", "catch", "class", "const", "continue", "debugger",
        "default", "delete", "do", "else", "export", "extends", "finally",
        "for", "function", "if", "import", "in", "instanceof", "new", "return",
        "super", "switch", "this", "throw", "try", "typeof", "var", "void",
        "while", "with", "yield", "let", "static", "enum", "await", "async",
        "type", "interface", "namespace", "declare", "abstract", "as", "from",
        "true", "false", "null", "undefined"
    }

    @classmethod
    def check_changed_files(cls, changed_files: List[ChangedFile], language: str = None) -> List[Dict[str, Any]]:
        findings = []

        for cf in changed_files:
            file_path = cf.new_path or cf.old_path or ""
            file_path_lower = file_path.lower()

            # Determine effective language for file
            file_lang = None
            if file_path_lower.endswith(".py"):
                file_lang = "python"
            elif file_path_lower.endswith((".java", ".jav")):
                file_lang = "java"
            elif file_path_lower.endswith((".ts", ".tsx")):
                file_lang = "typescript"
            elif file_path_lower.endswith((".js", ".jsx", ".mjs", ".cjs")):
                file_lang = "javascript"
            elif language:
                file_lang = language.lower()

            if file_lang == "python":
                findings.extend(cls._check_python_file(cf, file_path))
            elif file_lang == "java":
                findings.extend(cls._check_java_file(cf, file_path))
            elif file_lang in ("javascript", "typescript"):
                findings.extend(cls._check_js_ts_file(cf, file_path, file_lang))

        return findings

    @classmethod
    def _check_python_file(cls, cf: ChangedFile, file_path: str) -> List[Dict[str, Any]]:
        findings = []

        for item in cf.added_lines:
            line_no = item["line_no"]
            raw_content = item["content"]
            stripped = raw_content.strip()

            if not stripped:
                continue

            if stripped.startswith("#"):
                comment_text = stripped[1:].strip()
                if len(comment_text) > 8 and " " not in comment_text and not comment_text.startswith("http"):
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

            # Check 1: Unclosed Parentheses / Call Syntax removed to prevent false positives on multi-line statements.

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

    @classmethod
    def _check_java_file(cls, cf: ChangedFile, file_path: str) -> List[Dict[str, Any]]:
        findings = []
        has_try_in_hunks = any("try" in item["content"] for item in cf.added_lines)

        # Statement-based running parenthesis balance check
        paren_balance = 0
        statement_start_line = -1
        statement_text = ""
        
        for item in cf.added_lines:
            line_no = item["line_no"]
            content = item["content"]
            stripped = content.strip()
            
            if not stripped or stripped.startswith(("//", "/*", "*")):
                continue
                
            diff = stripped.count("(") - stripped.count(")")
            paren_balance += diff
            statement_text += content + "\n"
            
            if paren_balance > 0 and statement_start_line == -1:
                statement_start_line = line_no
                
            if stripped.endswith(";") or stripped.endswith("{") or stripped.endswith("}"):
                if paren_balance > 0 and statement_start_line != -1:
                    findings.append({
                        "file": file_path,
                        "line": statement_start_line,
                        "severity": "CRITICAL",
                        "category": "Syntax Error",
                        "rule_id": "SYNTAX-JAVA-UNCLOSED-PAREN-MULTILINE",
                        "message": f"Unclosed parenthesis in Java statement starting at line {statement_start_line}. Missing {paren_balance} closing parenthesis ')'.",
                        "suggestion": "Close the parenthesis properly before the statement ends.",
                        "fix_code": None,
                        "evidence": statement_text.strip(),
                        "is_blocking": True,
                        "source_tool": "syntax_checker"
                    })
                # Reset for next statement
                paren_balance = 0
                statement_start_line = -1
                statement_text = ""
            elif paren_balance <= 0:
                paren_balance = 0
                statement_start_line = -1
                statement_text = ""

        for item in cf.added_lines:
            line_no = item["line_no"]
            raw_content = item["content"]
            stripped = raw_content.strip()

            if not stripped:
                continue

            # 1. Check for Inline comment specificity / gibberish (JAVA-DOC-003)
            if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
                comment_text = stripped.lstrip("/*# ").rstrip("*/ ").strip()
                if len(comment_text) > 8 and " " not in comment_text and not comment_text.startswith("http"):
                    findings.append({
                        "file": file_path,
                        "line": line_no,
                        "severity": "WARNING",
                        "category": "Documentation",
                        "rule_id": "JAVA-DOC-003",
                        "message": f"Inline comment '{stripped}' appears to be meaningless gibberish. Comments should explain the 'Why' behind the code.",
                        "suggestion": "Remove the meaningless comment or replace it with a descriptive explanation.",
                        "fix_code": "",
                        "evidence": raw_content,
                        "is_blocking": False,
                        "source_tool": "syntax_checker"
                    })
                continue

            # Ignore annotations
            if stripped.startswith("@"):
                continue

            # 2. Check for Unclosed Parentheses (SYNTAX-JAVA-UNCLOSED-PAREN)
            # Only flag if the line explicitly ends with a semicolon, meaning the statement is supposedly complete but missing a parenthesis.
            diff_paren = stripped.count("(") - stripped.count(")")
            if diff_paren > 0 and stripped.endswith(";"):
                corrected = stripped + (")" * diff_paren)
                if not corrected.endswith(";"):
                    corrected += ";"
                findings.append({
                    "file": file_path,
                    "line": line_no,
                    "severity": "CRITICAL",
                    "category": "Syntax Error",
                    "rule_id": "SYNTAX-JAVA-UNCLOSED-PAREN",
                    "message": f"Unclosed parenthesis in Java statement '{stripped}' results in a fatal compilation error.",
                    "suggestion": f"Close the parenthesis to complete the expression: '{corrected}'.",
                    "fix_code": corrected,
                    "evidence": raw_content,
                    "is_blocking": True,
                    "source_tool": "syntax_checker"
                })
                continue

            # 3. Check for Stray Identifiers / Gibberish Tokens (SYNTAX-JAVA-STRAY-IDENTIFIER)
            # e.g. `hgjhgjhgkjhj` or `hgjhgjhgkjhj;` or solitary non-keyword word
            clean_word = stripped.rstrip(";").strip()
            if re.match(r'^[a-zA-Z_$][a-zA-Z0-9_$]*$', clean_word) and clean_word not in cls.JAVA_KEYWORDS:
                findings.append({
                    "file": file_path,
                    "line": line_no,
                    "severity": "CRITICAL",
                    "category": "Syntax Error",
                    "rule_id": "SYNTAX-JAVA-STRAY-IDENTIFIER",
                    "message": f"Stray invalid identifier '{stripped}' found outside of any assignment or method call. This causes a fatal Java compilation error.",
                    "suggestion": f"Remove the invalid stray text '{stripped}' from source code.",
                    "fix_code": "",
                    "evidence": raw_content,
                    "is_blocking": True,
                    "source_tool": "syntax_checker"
                })
                continue

            # 4. Check for Unclosed String Literal / Quotes (SYNTAX-JAVA-UNCLOSED-STRING)
            unescaped_quotes = len(re.findall(r'(?<!\\)"', stripped))
            if unescaped_quotes % 2 != 0:
                findings.append({
                    "file": file_path,
                    "line": line_no,
                    "severity": "CRITICAL",
                    "category": "Syntax Error",
                    "rule_id": "SYNTAX-JAVA-UNCLOSED-STRING",
                    "message": f"Unclosed string literal in statement '{stripped}'. Java requires double quotes to be matched.",
                    "suggestion": "Close the string literal or escape quotes properly.",
                    "fix_code": None,
                    "evidence": raw_content,
                    "is_blocking": True,
                    "source_tool": "syntax_checker"
                })
                continue

            # Single quotes enclosing multi-character string
            if re.search(r"(?<!\\)'[^']{2,}'", stripped):
                fixed_quotes = re.sub(r"(?<!\\)'([^']{2,})'", r'"\1"', stripped)
                findings.append({
                    "file": file_path,
                    "line": line_no,
                    "severity": "CRITICAL",
                    "category": "Syntax Error",
                    "rule_id": "SYNTAX-JAVA-MALFORMED-CHAR-LITERAL",
                    "message": f"Invalid character literal in statement '{stripped}'. In Java, single quotes are only for single characters ('c'). Use double quotes (\"...\") for strings.",
                    "suggestion": f"Replace single quotes with double quotes: '{fixed_quotes}'.",
                    "fix_code": fixed_quotes,
                    "evidence": raw_content,
                    "is_blocking": True,
                    "source_tool": "syntax_checker"
                })
                continue

            # 5. Check for Orphaned Catch / Finally without Try (SYNTAX-JAVA-ORPHAN-BLOCK)
            if stripped.startswith(("catch ", "catch(", "finally", "finally {")) and not has_try_in_hunks:
                findings.append({
                    "file": file_path,
                    "line": line_no,
                    "severity": "CRITICAL",
                    "category": "Syntax Error",
                    "rule_id": "SYNTAX-JAVA-ORPHAN-BLOCK",
                    "message": f"Orphaned '{stripped}' block found without a matching 'try' block.",
                    "suggestion": "Wrap the statement inside a proper 'try { ... }' block.",
                    "fix_code": None,
                    "evidence": raw_content,
                    "is_blocking": True,
                    "source_tool": "syntax_checker"
                })
                continue

            # 6. Check for Missing Semicolons on Executable Statements (SYNTAX-JAVA-MISSING-SEMICOLON)
            # Removed because line-by-line checking causes severe false positives on multi-line statements (like fluent builders). 
            # The AI LLM handles missing semicolons contextually via CODE_QUALITY_PROMPT.

        return findings

    # _is_java_statement_missing_semicolon removed to prevent false positives

    @classmethod
    def _check_js_ts_file(cls, cf: ChangedFile, file_path: str, lang: str = "javascript") -> List[Dict[str, Any]]:
        findings = []
        rule_prefix = "TS" if lang == "typescript" else "JS"

        # Statement-based running parenthesis balance check
        paren_balance = 0
        statement_start_line = -1
        statement_text = ""
        
        for item in cf.added_lines:
            line_no = item["line_no"]
            content = item["content"]
            stripped = content.strip()
            
            if not stripped or stripped.startswith(("//", "/*", "*")):
                continue
                
            diff = stripped.count("(") - stripped.count(")")
            paren_balance += diff
            statement_text += content + "\n"
            
            if paren_balance > 0 and statement_start_line == -1:
                statement_start_line = line_no
                
            if stripped.endswith(";") or stripped.endswith("{") or stripped.endswith("}"):
                if paren_balance > 0 and statement_start_line != -1:
                    findings.append({
                        "file": file_path,
                        "line": statement_start_line,
                        "severity": "CRITICAL",
                        "category": "Syntax Error",
                        "rule_id": f"SYNTAX-{rule_prefix}-UNCLOSED-PAREN-MULTILINE",
                        "message": f"Unclosed parenthesis in statement starting at line {statement_start_line}. Missing {paren_balance} closing parenthesis ')'.",
                        "suggestion": "Close the parenthesis properly.",
                        "fix_code": None,
                        "evidence": statement_text.strip(),
                        "is_blocking": True,
                        "source_tool": "syntax_checker"
                    })
                # Reset for next statement
                paren_balance = 0
                statement_start_line = -1
                statement_text = ""
            elif paren_balance <= 0:
                paren_balance = 0
                statement_start_line = -1
                statement_text = ""

        for item in cf.added_lines:
            line_no = item["line_no"]
            raw_content = item["content"]
            stripped = raw_content.strip()

            if not stripped:
                continue

            # 1. Inline comment check
            if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
                comment_text = stripped.lstrip("/*# ").rstrip("*/ ").strip()
                if len(comment_text) > 8 and " " not in comment_text and not comment_text.startswith("http"):
                    findings.append({
                        "file": file_path,
                        "line": line_no,
                        "severity": "WARNING",
                        "category": "Documentation",
                        "rule_id": f"{rule_prefix}-DOC-003",
                        "message": f"Inline comment '{stripped}' appears to be meaningless gibberish. Comments should explain the 'Why' behind the code.",
                        "suggestion": "Remove the meaningless comment or replace it with a descriptive explanation.",
                        "fix_code": "",
                        "evidence": raw_content,
                        "is_blocking": False,
                        "source_tool": "syntax_checker"
                    })
                continue

            # 2. Unclosed Parentheses
            # Only flag if the line explicitly ends with a semicolon, meaning the statement is supposedly complete but missing a parenthesis.
            diff_paren = stripped.count("(") - stripped.count(")")
            if diff_paren > 0 and stripped.endswith(";"):
                corrected = stripped + (")" * diff_paren)
                findings.append({
                    "file": file_path,
                    "line": line_no,
                    "severity": "CRITICAL",
                    "category": "Syntax Error",
                    "rule_id": f"SYNTAX-{rule_prefix}-UNCLOSED-PAREN",
                    "message": f"Unclosed parenthesis in statement '{stripped}' results in a SyntaxError.",
                    "suggestion": f"Close the parenthesis: '{corrected}'.",
                    "fix_code": corrected,
                    "evidence": raw_content,
                    "is_blocking": True,
                    "source_tool": "syntax_checker"
                })
                continue

            # 3. Stray Identifiers
            clean_word = stripped.rstrip(";").strip()
            if re.match(r'^[a-zA-Z_$][a-zA-Z0-9_$]*$', clean_word) and clean_word not in cls.JS_TS_KEYWORDS:
                findings.append({
                    "file": file_path,
                    "line": line_no,
                    "severity": "CRITICAL",
                    "category": "Syntax Error",
                    "rule_id": f"SYNTAX-{rule_prefix}-STRAY-IDENTIFIER",
                    "message": f"Stray invalid identifier '{stripped}' found outside of any assignment or call.",
                    "suggestion": f"Remove the invalid stray text '{stripped}' from source code.",
                    "fix_code": "",
                    "evidence": raw_content,
                    "is_blocking": True,
                    "source_tool": "syntax_checker"
                })
                continue

            # 4. Unclosed String Literal / Quotes
            unescaped_double = len(re.findall(r'(?<!\\)"', stripped))
            unescaped_single = len(re.findall(r"(?<!\\)'", stripped))
            unescaped_backtick = len(re.findall(r'(?<!\\)`', stripped))
            if (unescaped_double % 2 != 0) or (unescaped_single % 2 != 0) or (unescaped_backtick % 2 != 0):
                findings.append({
                    "file": file_path,
                    "line": line_no,
                    "severity": "CRITICAL",
                    "category": "Syntax Error",
                    "rule_id": f"SYNTAX-{rule_prefix}-UNCLOSED-STRING",
                    "message": f"Unclosed string or template literal in statement '{stripped}'.",
                    "suggestion": "Ensure matching quote or backtick closures.",
                    "fix_code": None,
                    "evidence": raw_content,
                    "is_blocking": True,
                    "source_tool": "syntax_checker"
                })
                continue

        return findings

