import re
from typing import Tuple

class InputRails:
    """Detects and neutralizes prompt injection and policy override attempts in acceptance criteria or code."""

    INJECTION_PATTERNS = [
        r"(?i)ignore\s+(?:all\s+)?(?:previous|prior|system)\s+instructions",
        r"(?i)override\s+(?:review\s+)?(?:readiness|policy|rules)",
        r"(?i)always\s+(?:say|return|output)\s+READY",
        r"(?i)mark\s+(?:this\s+)?(?:as\s+)?(?:READY|PASS|APPROVED)",
        r"(?i)system\s*:\s*you\s+are",
        r"(?i)<\|im_start\|>",
        r"(?i)do\s+not\s+report\s+any\s+(?:bugs|vulnerabilities|issues)"
    ]

    @classmethod
    def validate_acceptance_criteria(cls, text: str) -> Tuple[bool, str]:
        """Validates acceptance criteria for safety and injection attacks."""
        if not text:
            return True, ""
        
        for pattern in cls.INJECTION_PATTERNS:
            if re.search(pattern, text):
                sanitized = re.sub(pattern, "[MALICIOUS_OVERRIDE_FILTERED]", text)
                return False, sanitized

        return True, text

    @classmethod
    def sanitize_input(cls, text: str) -> str:
        """Sanitizes text by stripping out known adversarial delimiters."""
        if not text:
            return ""
        sanitized = text
        for pattern in cls.INJECTION_PATTERNS:
            sanitized = re.sub(pattern, "[FILTERED_PROMPT_INJECTION]", sanitized)
        return sanitized
