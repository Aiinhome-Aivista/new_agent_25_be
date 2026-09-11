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
        acceptance_criteria: List[Dict[str, Any]]
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
        standards = standards_store.search_relevant_standards(query=raw_diff[:1000] + " testing test rules")
        standards_text = "\n".join([f"- [{s['rule_code']}] {s['title']}: {s['description']}" for s in standards if "test" in s.get("category", "").lower() or "test" in s.get("title", "").lower()])

        prompt = TEST_COVERAGE_PROMPT.format(
            standards_text=standards_text,
            criteria_json=json.dumps(acceptance_criteria, indent=2),
            diff_text=raw_diff[:6000]
        )

        resp = LLMProvider.generate(prompt)
        missing_tests = resp.get("missingTests", [])

        # If source files were changed but NO test files exist, enforce at least one missing test warning
        if source_files_observed and not test_files_observed and not missing_tests:
            target_f = source_files_observed[0]
            missing_tests.append({
                "scenario_type": "happy_path",
                "target_file": target_f,
                "target_method": "coreMethods",
                "description": f"No unit tests were observed in this diff for modified source file: {target_f}.",
                "suggested_test_code": "// TODO: Add JUnit test verifying success path\n@Test\nvoid shouldExecuteSuccessfully() { ... }",
                "priority": "HIGH"
            })

        formatted_missing = []
        for mt in missing_tests:
            if isinstance(mt, dict):
                formatted_missing.append({
                    "scenario_type": mt.get("scenario_type", "edge_case"),
                    "target_file": mt.get("target_file", source_files_observed[0] if source_files_observed else "App.java"),
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
