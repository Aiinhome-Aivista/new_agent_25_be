import json
from typing import Dict, Any, List
from app.llm.provider import LLMProvider
from app.llm.prompts import TEST_COVERAGE_PROMPT
from app.rag.standards_store import standards_store
from app.tools.git_tool import ChangedFile

class TestCoverageAgent:
    """Analyzes test coverage in the diff and identifies missing edge case / unit test scenarios."""

    @staticmethod
    def derive_test_file_path(source_file: str, language: str = "general") -> str:
        if not source_file:
            return "src/test/java/com/example/Test.java" if "java" in (language or "").lower() else "tests/test_main.py"
        
        s = source_file.replace("\\", "/")
        # If already a test file, return as is
        if any(k in s.lower() for k in ["test", "spec", "__test__"]):
            return s

        lang_lower = (language or "").lower()
        if "java" in lang_lower:
            if "src/main/java/" in s:
                t = s.replace("src/main/java/", "src/test/java/")
            elif s.startswith("src/"):
                t = s.replace("src/", "src/test/java/")
            else:
                t = "src/test/java/" + s
            
            if t.endswith(".java"):
                base = t[:-5]
                if not base.endswith("Test"):
                    t = f"{base}Test.java"
            return t
        elif "python" in lang_lower:
            parts = s.split("/")
            filename = parts[-1]
            dirpath = "/".join(parts[:-1])
            test_filename = f"test_{filename}" if not filename.startswith("test_") else filename
            return f"tests/{test_filename}" if not dirpath.startswith("tests") else f"{dirpath}/{test_filename}"
        elif "typescript" in lang_lower or "javascript" in lang_lower:
            for ext in [".tsx", ".ts", ".jsx", ".js"]:
                if s.endswith(ext):
                    base = s[:-len(ext)]
                    return f"{base}.test{ext}"
            return f"{s}.test.ts"
        return s

    @staticmethod
    def _sanitize_test_code(code: str) -> str:
        if not code or not isinstance(code, str):
            return ""
        c = code.strip()
        # Remove markdown code fences if wrapped by LLM
        if c.startswith("```"):
            lines = c.split("\n")
            if len(lines) >= 2 and lines[0].startswith("```"):
                if lines[-1].strip() == "```":
                    c = "\n".join(lines[1:-1]).strip()
                else:
                    c = "\n".join(lines[1:]).strip()
        return c

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
            target_f = cls.derive_test_file_path(source_files_observed[0], language)
            lang_lower = (language or "").lower()
            if "python" in lang_lower:
                sample_test = "@pytest.mark.unit\ndef test_feature_execution_successfully():\n    # Given / Arrange\n    expected_result = True\n\n    # When / Act\n    actual_result = True\n\n    # Then / Assert\n    assert actual_result == expected_result"
            elif "typescript" in lang_lower or "javascript" in lang_lower:
                sample_test = "import { describe, it, expect } from 'vitest';\n\ndescribe('Feature Test', () => {\n  it('should execute successfully with valid parameters', () => {\n    // Given / Arrange\n    const input = true;\n\n    // When / Act & Assert\n    expect(input).toBe(true);\n  });\n});"
            elif "java" in lang_lower:
                sample_test = "@Test\n@DisplayName(\"Should execute successfully with valid inputs\")\nvoid shouldExecuteSuccessfully() {\n    // Given\n    boolean condition = true;\n\n    // When / Then\n    assertTrue(condition, \"Expected execution condition to be true\");\n}"
            elif "go" in lang_lower:
                sample_test = "func TestFeatureExecution(t *testing.T) {\n    // Given / Arrange\n    expected := true\n\n    // When & Then\n    if !expected {\n        t.Errorf(\"expected true, got false\")\n    }\n}"
            elif "csharp" in lang_lower or "cs" in lang_lower:
                sample_test = "[Fact]\npublic void ShouldExecuteSuccessfully() {\n    // Arrange, Act, Assert\n    Assert.True(true);\n}"
            else:
                sample_test = "// TODO: Add automated unit test covering this change"

            missing_tests.append({
                "scenario_type": "happy_path",
                "target_file": target_f,
                "target_method": "coreMethods",
                "description": f"No automated unit tests observed in this diff for modified source file: {source_files_observed[0]}.",
                "suggested_test_code": sample_test,
                "priority": "HIGH"
            })

        formatted_missing = []
        for mt in missing_tests:
            if isinstance(mt, dict):
                raw_target = mt.get("target_file") or (source_files_observed[0] if source_files_observed else "main.py")
                resolved_target = cls.derive_test_file_path(raw_target, language)
                clean_code = cls._sanitize_test_code(mt.get("suggested_test_code", "// Test code recommendation"))

                formatted_missing.append({
                    "scenario_type": mt.get("scenario_type", "edge_case"),
                    "target_file": resolved_target,
                    "target_method": mt.get("target_method"),
                    "description": mt.get("description", "Missing test scenario"),
                    "suggested_test_code": clean_code,
                    "priority": mt.get("priority", "MEDIUM")
                })

        return {
            "has_tests_in_diff": len(test_files_observed) > 0,
            "test_files_observed": test_files_observed,
            "missing_tests": formatted_missing
        }
