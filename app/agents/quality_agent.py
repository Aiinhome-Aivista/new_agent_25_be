import json
from typing import Dict, Any, List
from app.llm.provider import LLMProvider
from app.llm.prompts import CODE_QUALITY_PROMPT
from app.rag.standards_store import standards_store
from app.tools.secret_scanner import SecretScanner
from app.tools.sast_scanner import SASTScanner
from app.tools.syntax_checker import SyntaxChecker
from app.guardrails.validator import FindingValidator
from app.tools.git_tool import ChangedFile

class CodeQualityAgent:
    """Evaluates code quality, architectural standards, security rules, and error handling."""

    @classmethod
    def execute(
        cls,
        changed_files: List[ChangedFile],
        raw_diff: str,
        acceptance_criteria: List[Dict[str, Any]],
        language: str = "java",
        language_version: str = "",
        framework: str = "spring-boot",
        codebase_context: str = ""
    ) -> Dict[str, Any]:
        all_raw_findings: List[Dict[str, Any]] = []
        passed_checks: List[Dict[str, Any]] = []

        # 0. Deterministic Syntax / AST Checker
        syntax_findings = SyntaxChecker.check_changed_files(changed_files, language=language)
        all_raw_findings.extend(syntax_findings)

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
                "fix_code": sast.fix_code,
                "evidence": sast.evidence,
                "is_blocking": sast.is_blocking,
                "source_tool": "deterministic_sast"
            })

        # 3. RAG Retrieval for relevant standards
        standards = standards_store.search_relevant_standards(language=language, framework=framework, query=raw_diff[:1000])
        standards_text = "\n".join([f"- [{s['rule_code']}] {s['title']}: {s['description']}" for s in standards])

        if language_version:
            standards_text += f"\n- [LANG-VERSION-01] Strict Version Compliance: You MUST enforce {language} {language_version} features. If old syntax is used (e.g., prior to {language_version}), you MUST report it as an issue and provide the modernized code."


        # 4. Format annotated diff with real line numbers for exact LLM grounding
        annotated_diff = cls._format_annotated_diff(changed_files, raw_diff, max_chars=8000)

        # 5. LLM Code Quality & Standards Reasoning
        prompt = CODE_QUALITY_PROMPT.format(
            language=language,
            language_version=language_version,
            framework=framework or "standard",
            standards_text=standards_text,
            codebase_context=codebase_context if codebase_context else "(Codebase not indexed — index workspace for full context-aware review)",
            criteria_json=json.dumps(acceptance_criteria, indent=2),
            diff_text=annotated_diff
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

    @classmethod
    def _format_annotated_diff(cls, changed_files: List[ChangedFile], raw_diff: str, max_chars: int = 8000) -> str:
        """Formats git diff with exact real line numbers explicitly prefixed on every line for LLM grounding."""
        if not changed_files:
            return raw_diff[:max_chars]

        sections = []
        for cf in changed_files:
            file_name = cf.new_path or cf.old_path
            sections.append(f"### File: {file_name} ({cf.status})")
            if cf.hunks:
                for hunk in cf.hunks:
                    curr_line = hunk.new_start
                    sections.append(f"Hunk @@ -{hunk.old_start},{hunk.old_count} +{hunk.new_start},{hunk.new_count} @@:")
                    for line in hunk.lines:
                        if hasattr(line, 'line_type') and line.line_type == '+':
                            val = line.value if hasattr(line, 'value') else str(line)
                            sections.append(f"Line {curr_line}: + {val}")
                            curr_line += 1
                        elif isinstance(line, str) and line.startswith('+') and not line.startswith('+++'):
                            sections.append(f"Line {curr_line}: + {line[1:]}")
                            curr_line += 1
                        elif (hasattr(line, 'line_type') and line.line_type == '-') or (isinstance(line, str) and line.startswith('-') and not line.startswith('---')):
                            val = line.value if hasattr(line, 'value') else (line[1:] if isinstance(line, str) else str(line))
                            sections.append(f"        - {val}")
                        else:
                            val = line.value if hasattr(line, 'value') else (line[1:] if isinstance(line, str) and line.startswith(' ') else str(line))
                            sections.append(f"Line {curr_line}:   {val}")
                            curr_line += 1
            elif cf.added_lines:
                for item in cf.added_lines:
                    sections.append(f"Line {item['line_no']}: + {item['content']}")

        formatted = "\n".join(sections)
        if len(formatted) > max_chars:
            return formatted[:max_chars] + "\n... [diff truncated for length]"
        return formatted if formatted.strip() else raw_diff[:max_chars]

