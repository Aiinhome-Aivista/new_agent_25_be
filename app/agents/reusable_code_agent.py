import json
from typing import Dict, Any, List
from app.llm.provider import LLMProvider
from app.llm.prompts import REUSABLE_CODE_PROMPT

class ReusableCodeAgent:
    """Agent responsible for identifying modular, reusable code components in the git diff."""

    @classmethod
    def execute(cls, raw_diff: str, language: str, framework: str) -> List[Dict[str, Any]]:
        if not raw_diff or not raw_diff.strip():
            return []
            
        truncated_diff = raw_diff[:8000]
        prompt = REUSABLE_CODE_PROMPT.format(
            language=language,
            framework=framework or "standard",
            diff_text=truncated_diff
        )

        response = LLMProvider.generate(prompt)
        return response.get("reusable_components", [])
