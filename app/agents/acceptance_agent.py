import json
from typing import Dict, Any, List
from app.llm.provider import LLMProvider
from app.llm.prompts import ACCEPTANCE_CRITERIA_PROMPT
from app.guardrails.input_rails import InputRails

class AcceptanceCriteriaAgent:
    """Parses user stories and acceptance criteria into structured, verifiable conditions."""

    @classmethod
    def execute(cls, raw_criteria: str) -> Dict[str, Any]:
        if not raw_criteria or not raw_criteria.strip():
            return {
                "criteria": [],
                "ambiguities": ["No acceptance criteria provided by developer."],
                "has_criteria": False
            }

        # Step 1: Input Rail validation
        is_safe, sanitized = InputRails.validate_acceptance_criteria(raw_criteria)
        
        # Step 2: Format prompt and call LLM
        prompt = ACCEPTANCE_CRITERIA_PROMPT.format(criteria_text=sanitized)
        response = LLMProvider.generate(prompt)

        criteria_list = response.get("criteria", [])
        ambiguities = response.get("ambiguities", [])

        # Fallback formatting if list was raw strings
        formatted_criteria = []
        for idx, item in enumerate(criteria_list):
            if isinstance(item, dict):
                formatted_criteria.append({
                    "id": item.get("id", f"AC-{idx+1:03d}"),
                    "description": item.get("description", str(item)),
                    "checkableCondition": item.get("checkableCondition", item.get("description", "")),
                    "priority": item.get("priority", "HIGH")
                })
            elif isinstance(item, str):
                formatted_criteria.append({
                    "id": f"AC-{idx+1:03d}",
                    "description": item,
                    "checkableCondition": item,
                    "priority": "HIGH"
                })

        return {
            "criteria": formatted_criteria,
            "ambiguities": ambiguities,
            "has_criteria": len(formatted_criteria) > 0
        }
