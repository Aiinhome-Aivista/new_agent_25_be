from typing import List, Dict, Any, Set
from backend.app.schemas.review_schemas import GroundedIssueSchema
from backend.app.tools.secret_scanner import SecretScanner
from backend.app.tools.git_tool import ChangedFile

class FindingValidator:
    """Validates that AI-generated and deterministic issues are strictly grounded in observed diff context."""

    @staticmethod
    def validate_and_ground_findings(
        raw_findings: List[Dict[str, Any]], 
        changed_files: List[ChangedFile]
    ) -> List[GroundedIssueSchema]:
        valid_findings: List[GroundedIssueSchema] = []
        observed_files_map: Dict[str, Set[int]] = {}

        # Build mapping of observed files and valid line numbers from diff
        for cf in changed_files:
            file_name = cf.new_path or cf.old_path
            normalized_name = file_name.replace("\\", "/").lower()
            valid_lines: Set[int] = {0} # 0 is allowed for file-level issues
            
            for item in cf.added_lines:
                valid_lines.add(item["line_no"])
            
            # Also include hunk ranges
            for hunk in cf.hunks:
                for line_idx in range(hunk.new_start, hunk.new_start + hunk.new_count + 1):
                    valid_lines.add(line_idx)
            
            observed_files_map[normalized_name] = valid_lines
            # Also key by basename for flexible matching
            base_name = normalized_name.split("/")[-1]
            if base_name not in observed_files_map:
                observed_files_map[base_name] = valid_lines

        seen_keys: Set[str] = set()

        for finding in raw_findings:
            file_path = finding.get("file") or finding.get("file_path") or ""
            normalized_file = file_path.replace("\\", "/").lower()
            base_name = normalized_file.split("/")[-1] if normalized_file else ""

            # Check 1: File must be in the reviewed diff
            matched_lines = None
            actual_file_path = file_path
            for obs_file, lines in observed_files_map.items():
                if normalized_file == obs_file or normalized_file.endswith(obs_file) or obs_file.endswith(normalized_file) or base_name == obs_file:
                    matched_lines = lines
                    actual_file_path = file_path
                    break

            if matched_lines is None and observed_files_map:
                # If file not in diff, reject hallucinated file
                continue

            # Check 2: Line number verification
            line_no = int(finding.get("line") or finding.get("line_number") or 0)
            if matched_lines is not None and line_no not in matched_lines:
                # Snap to closest or file-level 0 if not inside hunk
                line_no = 0

            # Check 3: Redact any accidental secret values in message or evidence
            message = SecretScanner.redact_text(str(finding.get("message", "")).strip())
            suggestion = SecretScanner.redact_text(str(finding.get("suggestion", "")).strip())
            evidence = SecretScanner.redact_text(str(finding.get("evidence", "")).strip())
            severity = str(finding.get("severity", "WARNING")).upper()
            if severity not in ("INFO", "WARNING", "ERROR", "CRITICAL"):
                severity = "WARNING"
            
            category = str(finding.get("category", "Quality")).strip()
            rule_id = finding.get("rule_id")
            is_blocking = finding.get("is_blocking", severity in ("ERROR", "CRITICAL"))

            # Deduplication key
            dup_key = f"{actual_file_path}:{line_no}:{category}:{message[:40]}"
            if dup_key in seen_keys:
                continue
            seen_keys.add(dup_key)

            if not message or not suggestion:
                continue

            valid_findings.append(GroundedIssueSchema(
                file=actual_file_path or "workspace",
                line=line_no,
                severity=severity,
                category=category,
                rule_id=rule_id,
                message=message,
                suggestion=suggestion,
                evidence=evidence or "Observed in code diff",
                is_blocking=is_blocking,
                source_tool=finding.get("source_tool", "agent")
            ))

        return valid_findings
