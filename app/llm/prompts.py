# Prompt Templates with Strict JSON Output Specifications

ACCEPTANCE_CRITERIA_PROMPT = """You are an expert Acceptance Criteria Analysis Agent.
Analyze the user story and acceptance criteria provided below.

Convert the requirements into structured, checkable conditions. If criteria are unclear or missing, identify the ambiguities. Do NOT invent criteria that are not present.

Input Criteria:
{criteria_text}

Respond ONLY with a valid JSON object matching this schema:
{{
  "criteria": [
    {{
      "id": "AC-001",
      "description": "Brief description of criterion",
      "checkableCondition": "Explicit verifiable behavior to look for in code",
      "priority": "HIGH" // HIGH, MEDIUM, or LOW
    }}
  ],
  "ambiguities": []
}}
"""

CODE_QUALITY_PROMPT = """You are a Senior Staff Code Reviewer and Quality Agent.
Review the following Git diff and context for correctness, coding standards, maintainability, error handling, validation, performance, and security.

Coding Standards / RAG Rules:
{standards_text}

Acceptance Criteria:
{criteria_json}

Git Diff:
```diff
{diff_text}
```

Rules:
1. Ground every finding strictly in the observed code above.
2. Reference ONLY actual file paths and line numbers observed in the diff.
3. If an issue is general to the file, use line: 0.
4. Do NOT hallucinate unobserved files or non-existent methods.
5. Provide clear, actionable remediation suggestions with code snippets.

Respond ONLY with a valid JSON object matching this schema:
{{
  "issues": [
    {{
      "file": "file/path.java",
      "line": 42,
      "severity": "WARNING", // INFO, WARNING, ERROR, CRITICAL
      "category": "Quality", // Security, Acceptance Criteria, Quality, Standards, Error Handling
      "message": "Specific issue grounded in observed code.",
      "suggestion": "Actionable remediation advice.",
      "evidence": "Observed code snippet from diff",
      "is_blocking": false
    }}
  ],
  "passedChecks": [
    {{
      "check_name": "Name of check passed",
      "category": "Quality",
      "description": "Why it meets the standard"
    }}
  ]
}}
"""

TEST_COVERAGE_PROMPT = """You are an automated Test Coverage Analysis Agent.
Examine the following Git diff and acceptance criteria.
Identify if adequate unit/integration tests exist in the changed code, and list missing test scenarios (happy path, negative path, edge cases, error conditions).

Testing Standards / Rules:
{standards_text}

Acceptance Criteria:
{criteria_json}

Git Diff:
```diff
{diff_text}
```

Rules:
1. Check if test files (e.g. *Test.java, *Spec.groovy, test_*.py) are modified or present in the diff.
2. Do NOT claim a test exists if no test file is in the diff.
3. Propose realistic test scenarios and sample JUnit/pytest test methods.

Respond ONLY with a valid JSON object matching this schema:
{{
  "missingTests": [
    {{
      "scenario_type": "negative_path", // happy_path, negative_path, edge_case, regression
      "target_file": "src/main/java/...",
      "target_method": "methodName",
      "description": "Scenario description (e.g., should reject null email)",
      "suggested_test_code": "@Test void shouldThrowWhenEmailNull() {{ ... }}",
      "priority": "HIGH" // HIGH, MEDIUM, LOW
    }}
  ],
  "testsObserved": false
}}
"""

SUMMARY_FEEDBACK_PROMPT = """You are a Lead Software Architect generating a Pre-Push Code Review Summary.
Summarize the review findings grounded in the diff.

Diff Summary:
{diff_summary}

Issues Count:
Blocking: {blocking_count}, Warnings: {warning_count}, Missing Tests: {missing_tests_count}

Deterministic Push Readiness Verdict: {push_readiness}

Generate a concise, professional executive summary (2-4 sentences) highlighting the key strengths and immediate action items for the developer before pushing.

Respond ONLY with a JSON object:
{{
  "summary": "Concise grounded summary text."
}}
"""
