# Prompt Templates with Strict JSON Output Specifications

ACCEPTANCE_CRITERIA_PROMPT = """You are an expert Acceptance Criteria Analysis Agent.
Analyze the user story and acceptance criteria provided below.

Your task is to convert the requirements into structured, highly specific, and checkable conditions. 
If criteria are unclear, overly broad, or missing, identify the ambiguities. 
Do NOT invent or assume criteria that are not present in the input.

Input Criteria:
{criteria_text}

Respond ONLY with a valid JSON object matching this exact schema (no markdown wrapping, no explanation):
{{
  "criteria": [
    {{
      "id": "AC-001",
      "description": "Brief description of criterion",
      "checkableCondition": "Explicit verifiable behavior to look for in code",
      "priority": "HIGH" // HIGH, MEDIUM, or LOW
    }}
  ],
  "ambiguities": [
    "List any unclear or conflicting requirements here"
  ]
}}
"""

AC_VERIFICATION_PROMPT = """You are an expert Acceptance Criteria Verification Agent.
Your task is to analyze the Git diff and determine if the provided acceptance criteria have been fully, partially, or not satisfied by the code changes.

Acceptance Criteria:
{criteria_json}

Git Diff:
```diff
{diff_text}
```

For each criterion, carefully evaluate the code changes and provide a detailed verification result. Do NOT hallucinate evidence. If the required logic is missing, accurately report it.

Respond ONLY with a valid JSON object matching this exact schema (no markdown wrapping, no explanation):
{{
  "verified_criteria": [
    {{
      "criterion_id": "AC-001",
      "description": "Criterion description",
      "checkable_condition": "Checkable condition",
      "is_satisfied": true,
      "status": "SATISFIED", // SATISFIED, NOT_SATISFIED, or PARTIAL
      "evidence": "Observed code lines proving satisfaction or violation",
      "missing_details": "If not satisfied, what specific logic/validation is missing in the code?",
      "relevant_files": ["file1.py", "file2.py"]
    }}
  ]
}}
"""

CODE_QUALITY_PROMPT = """You are a Principal Software Engineer and Staff Security Code Reviewer.
Perform an exhaustive inspection of the following Git diff for bugs, syntax mistakes, typos, security flaws, performance bottlenecks, and architectural standards.

Target Language: {language}
Target Framework: {framework}

Coding Standards & RAG Context:
{standards_text}

Acceptance Criteria:
{criteria_json}

Git Diff:
```diff
{diff_text}
```

Critical Review Guidelines:
1. Exhaustive Inspection: Examine the entire diff line by line. If the diff contains multiple distinct errors/bugs across different lines, you MUST report ALL of them as separate entries in the `issues` array.
2. Defect Scope: Inspect modified code for:
   - Syntax errors, stray tokens, gibberish identifiers, typos, and bad conventions (e.g. stray text like `hgjhgjhgkjhj` -> report as Syntax Error with fix to delete it, `if name == " main ":` -> `if __name__ == "__main__":`).
   - Meaningless or gibberish inline comments (e.g., `#kjhgkjgh;kjbhg`) should be reported as Rule ID `PY-DOC-003` (Inline Comment Specificity) with a fix to delete them. Do NOT treat comments as code or unused variables.
   - Security vulnerabilities (e.g. binding to 0.0.0.0, SQL injection, eval/exec execution, secrets/tokens, command injection, XSS).
   - Logic bugs, runtime exceptions, missing null/type checks, unhandled edge cases.
   - Resource management (unclosed sockets, connections, files).
   - Ignore minor formatting, spacing, or whitespace issues (like empty lines). Do NOT report them as issues.
3. Grounding & Specificity:
   - Every issue MUST reference the EXACT line number where the defect is located in the diff.
   - Do NOT invent or hallucinate whole-file / line 0 generic textbook rules (e.g. 'avoid queries in loops', 'avoid hardcoding secrets') unless that exact defect is explicitly written in the added diff lines!
4. For EVERY detected issue:
   - Explain clearly WHY it is an issue in `message`.
   - Provide concrete, step-by-step remediation advice in `suggestion`.
   - `fix_code` MUST BE EXCLUSIVELY VALID EXECUTABLE CODE (e.g. `if __name__ == "__main__":` or `host=os.getenv("HOST", "127.0.0.1")` or `""` to remove a stray line). NEVER write plain English sentences or explanations in `fix_code`! If no single-line/block code replacement is applicable, set `"fix_code": null`.

Respond ONLY with a valid JSON object matching this exact schema (no markdown wrapping, no explanation):
{{
  "issues": [
    {{
      "file": "path/to/file.py",
      "line": 107,
      "severity": "CRITICAL", // INFO, WARNING, ERROR, CRITICAL
      "category": "Quality", // Security, Quality, Standards, Bug, Error Handling
      "rule_id": "QUAL-PY-SYNTAX-01",
      "message": "Detailed description of the issue grounded in diff.",
      "suggestion": "Clear, actionable explanation on how to fix it.",
      "fix_code": "if __name__ == \\"__main__\\":", // ONLY real code or null! NEVER English explanation text.
      "evidence": "Observed code snippet from diff",
      "is_blocking": false
    }}
  ],
  "passedChecks": [
    {{
      "check_name": "Name of standard check passed",
      "category": "Quality",
      "description": "Why this change satisfies the standard."
    }}
  ]
}}
"""

TEST_COVERAGE_PROMPT = """You are an automated Test Coverage Analysis Agent.
Examine the following Git diff and acceptance criteria.
Identify if adequate unit/integration tests exist in the changed code, and list specific missing test scenarios (happy path, negative path, edge cases, error conditions).
Analyze the following Git diff and propose targeted, realistic unit/integration test cases.

Target Language: {language}
Target Framework: {framework}

Testing Rules & Standards:
{standards_text}

Acceptance Criteria:
{criteria_json}

Git Diff:
```diff
{diff_text}
```

Rules:
1. Propose missing test scenarios (happy path, negative path, edge cases, error conditions).
2. Provide REAL, ready-to-run test code in `suggested_test_code` matching the Target Language:
   - Python: use `pytest` (e.g. `def test_<name>(): ...`)
   - TypeScript / JavaScript: use `jest` / `vitest` (e.g. `test('<name>', () => {{ ... }})`)
   - Java: use JUnit 5 (e.g. `@Test void should...() {{ ... }}`)
   - Go: use standard `testing` (e.g. `func Test*(t *testing.T) {{ ... }}`)
3. Check if test files (e.g. *Test.java, *Spec.groovy, test_*.py, *.test.ts) are modified or present in the diff.
4. Do NOT claim a test exists if no corresponding test file is in the diff.
5. Propose highly realistic, context-aware test scenarios.
6. Ensure the suggested test code is syntactically valid for the target language and testing framework.

Respond ONLY with a valid JSON object matching this exact schema (no markdown wrapping, no explanation):
{{
  "missingTests": [
    {{
      "scenario_type": "negative_path", // happy_path, negative_path, edge_case, regression
      "target_file": "path/to/file.py",
      "target_method": "methodName",
      "description": "Specific scenario to test.",
      "suggested_test_code": "def test_should_reject_invalid():\\n    # Assert test condition",
      "priority": "HIGH" // HIGH, MEDIUM, LOW
    }}
  ],
  "testsObserved": false
}}
"""

SUMMARY_FEEDBACK_PROMPT = """You are a Lead Software Architect generating a Pre-Push Code Review Summary.
Synthesize the review findings into a concise, professional, and constructive summary.

Diff Summary:
{diff_summary}

Issues Count:
Blocking: {blocking_count}, Warnings: {warning_count}, Missing Tests: {missing_tests_count}

Deterministic Push Readiness Verdict: {push_readiness}

Generate a concise, professional executive summary (2-4 sentences) highlighting the key strengths and immediate action items for the developer before pushing. Maintain an encouraging yet firm tone regarding blockers or missing tests.

Respond ONLY with a valid JSON object matching this exact schema (no markdown wrapping, no explanation):
{{
  "summary": "Concise grounded summary text highlighting strengths and next steps."
}}
"""

RULE_VALIDATION_PROMPT = """You are an expert Software Architecture and Language validation agent.
Analyze the following coding standard rule to ensure it makes sense for the target programming language and framework.

Language: {language}
Framework: {framework}

Rule Title: {title}
Rule Description: {description}
Bad Example: {bad_example}
Good Example: {good_example}

Determine if this rule is applicable and valid for the specified language and framework. If it contains syntax, annotations, or concepts that belong to a completely different language (e.g. Java annotations in a Python rule), it is invalid.

Respond ONLY with a valid JSON object matching this schema:
{{
  "is_valid": true,
  "warning_message": "If is_valid is false, provide a clear explanation why. Otherwise, leave empty."
}}
"""

REUSABLE_CODE_PROMPT = """You are an expert Software Architect and Code Analyst.
Analyze the following Git diff to identify any highly modular, reusable components (such as utility functions, generic classes, or shared hooks) that have been added or modified.

Target Language: {language}
Target Framework: {framework}

Git Diff:
```diff
{diff_text}
```

Rules:
1. Identify components that are abstracted enough to be reused across different parts of the application or other projects.
2. Provide a clear description of what the component does and why it is reusable.
3. Extract the exact code snippet from the diff that represents this reusable component.
4. If no highly reusable components are found, return an empty list.

Respond ONLY with a valid JSON object matching this exact schema (no markdown wrapping, no explanation):
{{
  "reusable_components": [
    {{
      "name": "Component Name (e.g., formatDate, UseAuth)",
      "component_type": "FUNCTION", // e.g., FUNCTION, CLASS, HOOK, COMPONENT
      "description": "Clear explanation of what it does and why it's reusable.",
      "file_path": "path/to/file.py",
      "snippet": "The reusable code block"
    }}
  ]
}}
"""
