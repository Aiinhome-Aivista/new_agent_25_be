import json
from typing import Dict, Any, List
from app.llm.provider import LLMProvider
from app.llm.prompts import TEST_COVERAGE_PROMPT
from app.rag.standards_store import standards_store
from app.tools.git_tool import ChangedFile

class TestCoverageAgent:
    """Analyzes test coverage in the diff and identifies missing edge case / unit test scenarios."""

    @classmethod
    def execute(
        cls,
        changed_files: List[ChangedFile],
        raw_diff: str,
        acceptance_criteria: List[Dict[str, Any]],
        language: str = "python",
        framework: str = "standard"
    ) -> Dict[str, Any]:
        # Check if test files are modified in diff
        test_files_observed = []
        source_files_observed = []

        for cf in changed_files:
            p = (cf.new_path or cf.old_path).lower()
            if any(test_pattern in p for test_pattern in ["test", "spec", "tests", "__test__"]):
                test_files_observed.append(cf.new_path or cf.old_path)
            else:
                source_files_observed.append(cf.new_path or cf.old_path)

        # Fetch testing specific standards
        standards = standards_store.search_relevant_standards(language=language, framework=framework, query=raw_diff[:1000] + " testing test rules")
        standards_text = "\n".join([f"- [{s['rule_code']}] {s['title']}: {s['description']}" for s in standards if "test" in s.get("category", "").lower() or "test" in s.get("title", "").lower()])

        prompt = TEST_COVERAGE_PROMPT.format(
            language=language,
            framework=framework or "standard",
            standards_text=standards_text,
            criteria_json=json.dumps(acceptance_criteria, indent=2),
            diff_text=raw_diff[:6000]
        )

        resp = LLMProvider.generate(prompt)
        missing_tests = resp.get("missingTests", [])

        # If source files were changed but NO test files exist, generate language-appropriate test recommendation
        if source_files_observed and not test_files_observed and not missing_tests:
            target_f = source_files_observed[0]
            lang_lower = (language or "").lower()
            if "python" in lang_lower:
                sample_test = "import pytest\n\ndef test_feature_execution():\n    # Arrange & Act & Assert\n    assert True"
            elif "typescript" in lang_lower or "javascript" in lang_lower:
                sample_test = "import { describe, it, expect } from 'vitest';\n\ndescribe('Feature Test', () => {\n  it('should execute successfully', () => {\n    expect(true).toBe(true);\n  });\n});"
            elif "java" in lang_lower:
                sample_test = "@Test\nvoid shouldExecuteSuccessfully() {\n    // Arrange, Act, Assert\n}"
            elif "go" in lang_lower:
                sample_test = "func TestFeatureExecution(t *testing.T) {\n    // Assert\n}"
            else:
                sample_test = "// TODO: Add automated unit test covering this change"

            missing_tests.append({
                "scenario_type": "happy_path",
                "target_file": target_f,
                "target_method": "coreMethods",
                "description": f"No automated unit tests observed in this diff for modified source file: {target_f}.",
                "suggested_test_code": sample_test,
                "priority": "HIGH"
            })

        formatted_missing = []
        for mt in missing_tests:
            if isinstance(mt, dict):
                formatted_missing.append({
                    "scenario_type": mt.get("scenario_type", "edge_case"),
                    "target_file": mt.get("target_file", source_files_observed[0] if source_files_observed else "main.py"),
                    "target_method": mt.get("target_method"),
                    "description": mt.get("description", "Missing test scenario"),
                    "suggested_test_code": mt.get("suggested_test_code", "// Test code recommendation"),
                    "priority": mt.get("priority", "MEDIUM")
                })

        return {
            "has_tests_in_diff": len(test_files_observed) > 0,
            "test_files_observed": test_files_observed,
            "missing_tests": formatted_missing
        }
