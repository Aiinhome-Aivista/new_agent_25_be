import re
from typing import List, Dict, Any

class SASTFinding:
    def __init__(self, file: str, line: int, severity: str, rule_id: str, message: str, suggestion: str, evidence: str, is_blocking: bool = False):
        self.file = file
        self.line = line
        self.severity = severity # INFO, WARNING, ERROR, CRITICAL
        self.rule_id = rule_id
        self.message = message
        self.suggestion = suggestion
        self.evidence = evidence
        self.is_blocking = is_blocking

class SASTScanner:
    """Deterministic SAST engine focusing on Java/Spring Boot and general enterprise security rules."""

    JAVA_RULES = [
        {
            "id": "SEC-JAVA-SQLI-01",
            "name": "SQL Injection via String Concatenation",
            "pattern": r"""(?:createQuery|createNativeQuery|prepareStatement|executeLargeUpdate|executeQuery|jdbcTemplate\.query)\s*\(\s*["'].*?\+\s*[a-zA-Z0-9_]+""",
            "severity": "CRITICAL",
            "is_blocking": True,
            "message": "Detected dynamic SQL query construction using direct string concatenation.",
            "suggestion": "Use parameterized queries or JPA named parameters (e.g., :param) to prevent SQL injection."
        },
        {
            "id": "SEC-JAVA-CSRF-01",
            "name": "CSRF Protection Disabled",
            "pattern": r"""\.csrf\(\s*\)\s*\.disable\(\s*\)""",
            "severity": "WARNING",
            "is_blocking": False,
            "message": "Spring Security CSRF protection is explicitly disabled.",
            "suggestion": "Enable CSRF protection unless stateless JWT / token authentication is strictly enforced on all mutable endpoints."
        },
        {
            "id": "SEC-JAVA-DESER-01",
            "name": "Unsafe ObjectInputStream Deserialization",
            "pattern": r"""new\s+ObjectInputStream\s*\(""",
            "severity": "CRITICAL",
            "is_blocking": True,
            "message": "Unsafe Java native deserialization with ObjectInputStream detected.",
            "suggestion": "Avoid native Java deserialization of untrusted payloads; use JSON/Protobuf with strict schema validation."
        },
        {
            "id": "QUAL-JAVA-VALID-01",
            "name": "Missing @Valid on Request Body",
            "pattern": r"""@PostMapping|@PutMapping|@PatchMapping.*?public.*?(@RequestBody(?!\s*@Valid\s+)[A-Z][a-zA-Z0-9]+)""",
            "severity": "WARNING",
            "is_blocking": False,
            "message": "Controller endpoint accepts @RequestBody without @Valid or @Validated annotation.",
            "suggestion": "Annotate DTO parameter with @Valid or @Validated to enforce bean validation constraints."
        },
        {
            "id": "QUAL-JAVA-EXC-01",
            "name": "Empty Catch Block / Swallowed Exception",
            "pattern": r"""catch\s*\([A-Za-z0-9_]+\s+[a-zA-Z0-9_]+\)\s*\{\s*(?:\/\/.*|\/\*.*\*\/)?\s*\}""",
            "severity": "ERROR",
            "is_blocking": False,
            "message": "Empty catch block swallowed exception without logging or rethrowing.",
            "suggestion": "Log the exception with stack trace (e.g., log.error(\"Context\", e)) or rethrow a domain-specific exception."
        },
        {
            "id": "QUAL-JAVA-SYS-01",
            "name": "Direct System.out.println in Production Code",
            "pattern": r"""System\.(?:out|err)\.print(?:ln)?""",
            "severity": "WARNING",
            "is_blocking": False,
            "message": "Direct console logging with System.out/err found in source code.",
            "suggestion": "Use an enterprise logger like SLF4J (e.g., log.info(...), log.debug(...)) instead of standard output."
        }
    ]

    PYTHON_RULES = [
        {
            "id": "SEC-PY-SQLI-01",
            "name": "Python SQL Injection via F-Strings / Format Concatenation",
            "pattern": r"""(?:cursor\.execute|execute_query|db\.session\.execute)\s*\(\s*(?:f["']|["'].*?%s.*?["']\s*%)""",
            "severity": "CRITICAL",
            "is_blocking": True,
            "message": "Dynamic SQL query formed using f-string or string formatting in Python.",
            "suggestion": "Use parameterized queries with placeholders (e.g., cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))) to prevent SQL injection."
        },
        {
            "id": "SEC-PY-PICKLE-01",
            "name": "Unsafe Python Pickle Deserialization",
            "pattern": r"""\bpickle\.(?:loads|load)\s*\(""",
            "severity": "CRITICAL",
            "is_blocking": True,
            "message": "Unsafe Python pickle deserialization of untrusted data detected.",
            "suggestion": "Pickle allows arbitrary code execution. Use JSON, MsgPack, or Protocol Buffers instead."
        },
        {
            "id": "SEC-PY-YAML-01",
            "name": "Unsafe YAML Loader (Arbitrary Object Instantiation)",
            "pattern": r"""yaml\.load\s*\([^,)]*(?!,\s*Loader\s*=\s*(?:yaml\.)?SafeLoader)""",
            "severity": "CRITICAL",
            "is_blocking": True,
            "message": "Insecure yaml.load() detected without SafeLoader.",
            "suggestion": "Use yaml.safe_load() or specify Loader=yaml.SafeLoader."
        },
        {
            "id": "QUAL-PY-EXC-01",
            "name": "Bare Except Clause Swallowing Errors",
            "pattern": r"""except\s*:\s*(?:pass|return)""",
            "severity": "WARNING",
            "is_blocking": False,
            "message": "Bare except: block silently catches all exceptions including SystemExit and KeyboardInterrupt.",
            "suggestion": "Catch specific exception types (e.g., except ValueError as e:) and log the error."
        },
        {
            "id": "SEC-PY-DEBUG-01",
            "name": "Flask / Django Debug Mode Enabled",
            "pattern": r"""(?:app\.run\(.*?debug\s*=\s*True|DEBUG\s*=\s*True)""",
            "severity": "WARNING",
            "is_blocking": False,
            "message": "Debug mode explicitly enabled in production code.",
            "suggestion": "Set debug mode dynamically using environment variables (e.g., os.getenv('DEBUG', 'False').lower() == 'true')."
        }
    ]

    TYPESCRIPT_RULES = [
        {
            "id": "SEC-JS-HTML-01",
            "name": "Dangerous InnerHTML / XSS Risk",
            "pattern": r"""(?:dangerouslySetInnerHTML|innerHTML\s*=)""",
            "severity": "WARNING",
            "is_blocking": False,
            "message": "Direct HTML injection with dangerouslySetInnerHTML or innerHTML.",
            "suggestion": "Sanitize HTML using DOMPurify before rendering or use standard React text nodes to prevent XSS."
        }
    ]

    GENERIC_RULES = [
        {
            "id": "SEC-GEN-EVAL-01",
            "name": "Dangerous Eval / Dynamic Code Execution",
            "pattern": r"""\b(?:eval|exec)\s*\(""",
            "severity": "CRITICAL",
            "is_blocking": True,
            "message": "Direct dynamic execution (eval/exec) of code detected.",
            "suggestion": "Refactor to use deterministic logic and static parsers instead of eval/exec."
        },
        {
            "id": "SEC-GEN-CMDI-01",
            "name": "Command Injection Risk via Process Builder / Subprocess",
            "pattern": r"""(?:Runtime\.getRuntime\(\)\.exec|ProcessBuilder|os\.system|subprocess\.Popen\(.*?shell\s*=\s*True)""",
            "severity": "CRITICAL",
            "is_blocking": True,
            "message": "Shell execution or unescaped Process execution detected.",
            "suggestion": "Avoid invoking shell directly; pass argument list without shell=True and validate all inputs with strict allowlists."
        }
    ]

    @classmethod
    def scan_changed_files(cls, changed_files: List[Any]) -> List[SASTFinding]:
        findings: List[SASTFinding] = []
        all_rules = cls.JAVA_RULES + cls.PYTHON_RULES + cls.TYPESCRIPT_RULES + cls.GENERIC_RULES

        for f in changed_files:
            file_path = f.new_path or f.old_path
            for item in f.added_lines:
                line_no = item["line_no"]
                content = item["content"]

                for rule in all_rules:
                    if re.search(rule["pattern"], content, flags=re.IGNORECASE):
                        findings.append(SASTFinding(
                            file=file_path,
                            line=line_no,
                            severity=rule["severity"],
                            rule_id=rule["id"],
                            message=rule["message"],
                            suggestion=rule["suggestion"],
                            evidence=content.strip(),
                            is_blocking=rule.get("is_blocking", False)
                        ))
        return findings
