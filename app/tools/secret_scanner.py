import re
from typing import List, Dict, Any

class SecretFinding:
    def __init__(self, file: str, line: int, secret_type: str, raw_snippet: str, redacted_snippet: str):
        self.file = file
        self.line = line
        self.secret_type = secret_type
        self.raw_snippet = raw_snippet
        self.redacted_snippet = redacted_snippet

class SecretScanner:
    """Deterministic high-entropy and pattern-based secret scanner with mandatory LLM redaction."""

    PATTERNS = [
        ("AWS Access Key", r"(?:A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}"),
        ("Generic Private Key", r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
        ("Hardcoded API Key / Token", r"""(?i)(?:api_key|apikey|secret_key|auth_token|bearer|access_token|password|passwd|db_password)\s*[:=]\s*["']([A-Za-z0-9_\-\.\$\/\+]{8,128})["']"""),
        ("GitHub Personal Access Token", r"gh[pousr]_[A-Za-z0-9_]{36,255}"),
        ("Generic JWT Token", r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
        ("Slack Webhook / Token", r"https://hooks\.slack\.com/services/T[a-zA-Z0-9_]+/B[a-zA-Z0-9_]+/[a-zA-Z0-9_]+"),
    ]

    REDACTED_PLACEHOLDER = "********REDACTED********"

    @classmethod
    def scan_changed_files(cls, changed_files: List[Any]) -> List[SecretFinding]:
        findings: List[SecretFinding] = []

        for f in changed_files:
            file_path = f.new_path or f.old_path
            for item in f.added_lines:
                line_no = item["line_no"]
                content = item["content"]

                for label, pattern in cls.PATTERNS:
                    match = re.search(pattern, content)
                    if match:
                        matched_val = match.group(1) if match.groups() else match.group(0)
                        # Check for dummy/test placeholders
                        if any(dummy in matched_val.lower() for dummy in ["xxx", "test", "example", "placeholder", "your_", "<"]):
                            continue

                        redacted = content.replace(matched_val, cls.REDACTED_PLACEHOLDER)
                        findings.append(SecretFinding(
                            file=file_path,
                            line=line_no,
                            secret_type=label,
                            raw_snippet=content,
                            redacted_snippet=redacted
                        ))
        return findings

    @classmethod
    def redact_text(cls, text: str) -> str:
        """Redacts all potential secret patterns before sending any content to an LLM."""
        if not text:
            return text
        redacted = text
        for label, pattern in cls.PATTERNS:
            def replace_fn(m):
                full = m.group(0)
                if m.groups():
                    val = m.group(1)
                    return full.replace(val, cls.REDACTED_PLACEHOLDER)
                return cls.REDACTED_PLACEHOLDER
            redacted = re.sub(pattern, replace_fn, redacted)
        return redacted
