import json
from typing import Dict, Any, List
from backend.app.llm.provider import LLMProvider
from backend.app.llm.prompts import CODE_QUALITY_PROMPT
from backend.app.rag.standards_store import standards_store
from backend.app.tools.secret_scanner import SecretScanner
from backend.app.tools.sast_scanner import SASTScanner
from backend.app.guardrails.validator import FindingValidator
from backend.app.tools.git_tool import ChangedFile

class CodeQualityAgent:
    """Evaluates code quality, architectural standards, security rules, and error handling."""

    @classmethod
    def execute(
        cls,
        changed_files: List[ChangedFile],
        raw_diff: str,
        acceptance_criteria: List[Dict[str, Any]],
        language: str = "java",
        framework: str = "spring-boot"
    ) -> Dict[str, Any]:
        all_raw_findings: List[Dict[str, Any]] = []
        passed_checks: List[Dict[str, Any]] = []

        # 1. Deterministic Secret Scanner (Zero false negatives on known credential patterns)
        secret_findings = SecretScanner.scan_changed_files(changed_files)
        for sf in secret_findings:
            all_raw_findings.append({
                "file": sf.file,
                "line": sf.line,
                "severity": "CRITICAL",
                "category": "Security",
                "rule_id": "SEC-SECRET-LEAK",
                "message": f"High risk secret ({sf.secret_type}) exposed in source code.",
                "suggestion": "Extract secrets into environment variables, AWS Secrets Manager, or HashiCorp Vault. Never commit credentials.",
                "evidence": sf.redacted_snippet,
                "is_blocking": True,
                "source_tool": "secret_scanner"
            })

        # 2. Deterministic SAST Scanner
        sast_findings = SASTScanner.scan_changed_files(changed_files)
        for sast in sast_findings:
            all_raw_findings.append({
                "file": sast.file,
                "line": sast.line,
                "severity": sast.severity,
                "category": "Security" if "SEC" in sast.rule_id else "Quality",
                "rule_id": sast.rule_id,
                "message": sast.message,
                "suggestion": sast.suggestion,
                "evidence": sast.evidence,
                "is_blocking": sast.is_blocking,
                "source_tool": "deterministic_sast"
            })

        # 3. RAG Retrieval for relevant standards
        standards = standards_store.search_relevant_standards(language=language, framework=framework, query=raw_diff[:1000])
        standards_text = "\n".join([f"- [{s['rule_code']}] {s['title']}: {s['description']}" for s in standards])

        # 4. LLM Code Quality & Standards Reasoning
        truncated_diff = raw_diff[:8000] # Safe token limit
        prompt = CODE_QUALITY_PROMPT.format(
            standards_text=standards_text,
            criteria_json=json.dumps(acceptance_criteria, indent=2),
            diff_text=truncated_diff
        )

        llm_resp = LLMProvider.generate(prompt)
        llm_issues = llm_resp.get("issues", [])
        for issue in llm_issues:
            if isinstance(issue, dict):
                issue["source_tool"] = "ai_quality_agent"
                all_raw_findings.append(issue)

        for check in llm_resp.get("passedChecks", []):
            if isinstance(check, dict):
                passed_checks.append(check)

        if not secret_findings and not any(f["severity"] == "CRITICAL" for f in all_raw_findings):
            passed_checks.append({
                "check_name": "Deterministic Secret & Credential Scan",
                "category": "Security",
                "description": "No hardcoded private keys, access tokens, or credentials detected."
            })

        # 5. Finding Grounding and Hallucination Filter
        validated_findings = FindingValidator.validate_and_ground_findings(all_raw_findings, changed_files)

        return {
            "findings": [f.model_dump() for f in validated_findings],
            "passed_checks": passed_checks,
            "retrieved_standards": standards
        }
