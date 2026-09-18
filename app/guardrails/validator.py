import re
from typing import List, Dict, Any, Set
from app.schemas.review_schemas import GroundedIssueSchema
from app.tools.secret_scanner import SecretScanner
from app.tools.git_tool import ChangedFile

class FindingValidator:
    """Validates that AI-generated and deterministic issues are strictly grounded in observed diff context."""

    @staticmethod
    def _extract_topic(rule_id: str, message: str, evidence: str, fix_code: str) -> str:
        combined = f"{rule_id} {message} {evidence} {fix_code or ''}".lower()
        if "stray" in combined or "undefined identifier" in combined or "invalid identifier" in combined or "stray-identifier" in combined:
            return "stray_identifier"
        if "syntax error" in combined or "syntaxerror" in combined or "invalid syntax" in combined or "missing colon" in combined:
            return "syntax_error"
        if "dunder" in combined or "__name__" in combined or "main entrypoint" in combined or "if  name" in combined or "if name" in combined:
            return "dunder_main"
        if "unclosed paren" in combined or "syntax-py-unclosed-paren" in combined or "unclosed parenthesis" in combined:
            return "unclosed_parenthesis"
        if "0.0.0.0" in combined or "sec-py-host" in combined or "wildcard" in combined or "host binding" in combined:
            return "wildcard_host"
        if "import uvicorn" in combined or "missing-import-uvicorn" in combined or "nameerror: name 'uvicorn'" in combined:
            return "uvicorn_import"
        if "eval(" in combined or "exec(" in combined or "dynamic code execution" in combined:
            return "dynamic_eval"
        if "sqli" in combined or "sql injection" in combined:
            return "sql_injection"
        if "secret" in combined or "credential" in combined or "private key" in combined:
            return "secret_leak"
        if "bare except" in combined or "qual-py-exc" in combined:
            return "bare_except"
        return f"custom_{rule_id or message[:20]}"

    @staticmethod
    def validate_and_ground_findings(
        raw_findings: List[Dict[str, Any]], 
        changed_files: List[ChangedFile]
    ) -> List[GroundedIssueSchema]:
        valid_findings: List[GroundedIssueSchema] = []
        canonical_files_map: Dict[str, str] = {}
        observed_files_map: Dict[str, Set[int]] = {}
        added_lines_content_map: Dict[str, Dict[int, str]] = {}

        # Build mapping of observed files, valid line numbers, and line contents from diff
        for cf in changed_files:
            file_name = cf.new_path or cf.old_path
            normalized_name = file_name.replace("\\", "/").lower()
            canonical_files_map[normalized_name] = file_name
            valid_lines: Set[int] = {0} # 0 is allowed for file-level issues
            line_contents: Dict[int, str] = {}
            
            for item in cf.added_lines:
                l_no = item["line_no"]
                valid_lines.add(l_no)
                line_contents[l_no] = item["content"].strip()
            
            for hunk in cf.hunks:
                for line_idx in range(hunk.new_start, hunk.new_start + hunk.new_count + 1):
                    valid_lines.add(line_idx)
            
            observed_files_map[normalized_name] = valid_lines
            added_lines_content_map[normalized_name] = line_contents

            base_name = normalized_name.split("/")[-1]
            if base_name not in observed_files_map:
                observed_files_map[base_name] = valid_lines
                canonical_files_map[base_name] = file_name
                added_lines_content_map[base_name] = line_contents

        seen_line_keys: Set[str] = set()
        seen_topic_keys: Set[str] = set()
        severity_weights = {"CRITICAL": 4, "ERROR": 3, "WARNING": 2, "INFO": 1}

        for finding in raw_findings:
            file_path = finding.get("file") or finding.get("file_path") or ""
            normalized_file = file_path.replace("\\", "/").lower()
            base_name = normalized_file.split("/")[-1] if normalized_file else ""

            matched_lines = None
            actual_file_path = file_path
            matched_content_map = {}
            for obs_file, lines in observed_files_map.items():
                if normalized_file == obs_file or normalized_file.endswith(obs_file) or obs_file.endswith(normalized_file) or base_name == obs_file:
                    matched_lines = lines
                    actual_file_path = canonical_files_map.get(obs_file, file_path)
                    matched_content_map = added_lines_content_map.get(obs_file, {})
                    break

            if matched_lines is None and observed_files_map:
                continue

            line_no = int(finding.get("line") or finding.get("line_number") or 0)
            message = SecretScanner.redact_text(str(finding.get("message", "")).strip())
            suggestion = SecretScanner.redact_text(str(finding.get("suggestion", "")).strip())
            evidence = SecretScanner.redact_text(str(finding.get("evidence", "")).strip())
            fix_code_val = finding.get("fix_code")
            if fix_code_val == "":
                fix_code = ""
            elif fix_code_val:
                fix_code = SecretScanner.redact_text(str(fix_code_val).strip())
            else:
                fix_code = None

            # Clean English instructions out of fix_code
            if fix_code and fix_code != "":
                fc_lower = fix_code.lower()
                if (fc_lower.startswith(('ensure ', 'make sure ', 'you should ', 'please ', 'change ', 'consider ', 'it is recommended', 'replace the '))
                    or (' at the top of the file' in fc_lower)
                    or (' before the line' in fc_lower)):
                    fix_code = None

            # Smart line alignment: If line is blank or LLM was off-by-one, snap to the actual line matching evidence/message
            if line_no > 0 and matched_content_map:
                curr_content = matched_content_map.get(line_no, "")
                msg_lower = message.lower()
                if not curr_content or (evidence and evidence not in curr_content) or ("host" in msg_lower and "host" not in curr_content.lower()) or ("0.0.0.0" in msg_lower and "0.0.0.0" not in curr_content):
                    # Search diff lines for matching content
                    for candidate_line, line_text in matched_content_map.items():
                        lt_lower = line_text.lower()
                        if line_text and (line_text in evidence or (evidence and evidence in line_text) or 
                           ("if " in msg_lower and lt_lower.startswith("if ")) or
                           (("0.0.0.0" in msg_lower or "host" in msg_lower) and ("0.0.0.0" in lt_lower or "host" in lt_lower or "uvicorn" in lt_lower)) or
                           ("create_app" in msg_lower and "create_app" in lt_lower) or
                           ("parenthes" in msg_lower and ("(" in line_text or ")" in line_text))):
                            line_no = candidate_line
                            break

            if matched_lines is not None and line_no not in matched_lines:
                line_no = 0

            # Reject ungrounded line 0 findings that don't match any modified diff content
            if line_no == 0:
                if matched_content_map:
                    all_diff_text = " ".join(matched_content_map.values()).lower()
                    ev_lower = (evidence or "").lower()
                    msg_lower = (message or "").lower()
                    if not any(token in all_diff_text for token in ("password", "secret", "0.0.0.0", "eval(", "exec(", "select", "token") if token in ev_lower or token in msg_lower):
                        continue
                else:
                    continue

            severity = str(finding.get("severity", "WARNING")).upper()
            if severity not in ("INFO", "WARNING", "ERROR", "CRITICAL"):
                severity = "WARNING"
            
            category = str(finding.get("category", "Quality")).strip()
            rule_id = finding.get("rule_id")
            is_blocking = finding.get("is_blocking", severity in ("ERROR", "CRITICAL"))

            # Ensure fix_code is a complete line replacement if evidence contains uvicorn/app call
            if fix_code and evidence:
                ev_stripped = evidence.strip()
                if "0.0.0.0" in ev_stripped and ("host" in fix_code.lower() or "127.0.0.1" in fix_code):
                    if ("uvicorn.run" in ev_stripped or "app.run" in ev_stripped) and ("uvicorn.run" not in fix_code and "app.run" not in fix_code):
                        fix_code = re.sub(r"""['"]0\.0\.0\.0['"]""", '"127.0.0.1"', ev_stripped)

            candidate = GroundedIssueSchema(
                file=actual_file_path or "workspace",
                line=line_no,
                severity=severity,
                category=category,
                rule_id=rule_id,
                message=message,
                suggestion=suggestion,
                fix_code=fix_code,
                evidence=evidence or (matched_content_map.get(line_no) if line_no in matched_content_map else "Observed in code diff"),
                is_blocking=is_blocking,
                source_tool=finding.get("source_tool", "agent")
            )

            # Extract defect topic fingerprint per line
            topic = FindingValidator._extract_topic(rule_id or "", message, evidence, fix_code)
            topic_key = f"{actual_file_path}:{line_no}:{topic}" if line_no > 0 else f"{actual_file_path}:0:{topic}"
            line_key = f"{actual_file_path}:{line_no}:{rule_id or 'GEN'}" if line_no > 0 else f"{actual_file_path}:0:{category}:{message[:30]}"

            # Deduplication Check 1: Topic-level deduplication on the same line
            if topic_key in seen_topic_keys:
                for idx, existing in enumerate(valid_findings):
                    existing_topic = FindingValidator._extract_topic(existing.rule_id or "", existing.message, existing.evidence, existing.fix_code)
                    existing_topic_key = f"{existing.file}:{existing.line}:{existing_topic}" if existing.line > 0 else f"{existing.file}:0:{existing_topic}"
                    if existing_topic_key == topic_key:
                        cand_weight = severity_weights.get(candidate.severity, 1) + (3 if candidate.fix_code else 0)
                        exist_weight = severity_weights.get(existing.severity, 1) + (3 if existing.fix_code else 0)
                        # Prefer deterministic tools over AI hallucinations
                        if candidate.source_tool in ("syntax_checker", "secret_scanner", "deterministic_sast") and existing.source_tool not in ("syntax_checker", "secret_scanner", "deterministic_sast"):
                            valid_findings[idx] = candidate
                        elif cand_weight > exist_weight:
                            valid_findings[idx] = candidate
                        break
                continue

            # Deduplication Check 2: Exact File, Line & Rule deduplication
            if line_key in seen_line_keys:
                for idx, existing in enumerate(valid_findings):
                    existing_line_key = f"{existing.file}:{existing.line}:{existing.rule_id or 'GEN'}" if existing.line > 0 else f"{existing.file}:0:{existing.category}:{existing.message[:30]}"
                    if existing_line_key == line_key:
                        cand_weight = severity_weights.get(candidate.severity, 1) + (3 if candidate.fix_code else 0)
                        exist_weight = severity_weights.get(existing.severity, 1) + (3 if existing.fix_code else 0)
                        if candidate.source_tool in ("syntax_checker", "secret_scanner", "deterministic_sast") and existing.source_tool not in ("syntax_checker", "secret_scanner", "deterministic_sast"):
                            valid_findings[idx] = candidate
                        elif cand_weight > exist_weight:
                            valid_findings[idx] = candidate
                        break
                continue

            seen_line_keys.add(line_key)
            seen_topic_keys.add(topic_key)
            valid_findings.append(candidate)

        return valid_findings
