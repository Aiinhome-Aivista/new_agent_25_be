from typing import List, Dict, Any

class PushReadinessEngine:
    """Deterministic Rules Engine evaluating final Push-Readiness verdict and Risk Level."""

    @classmethod
    def evaluate(
        cls,
        findings: List[Dict[str, Any]],
        missing_tests: List[Dict[str, Any]],
        acceptance_results: List[Dict[str, Any]],
        has_diff: bool,
        has_criteria: bool
    ) -> Dict[str, Any]:
        if not has_diff:
            return {
                "push_readiness": "LIMITED_REVIEW",
                "risk_level": "UNKNOWN",
                "blocking_count": 0,
                "warning_count": 0,
                "reasons": ["No git diff was available to evaluate."]
            }

        blocking_count = 0
        warning_count = 0
        info_count = 0
        reasons = []

        # Analyze findings
        for f in findings:
            sev = f.get("severity", "WARNING").upper()
            is_blocking = f.get("is_blocking", False)

            if sev in ("CRITICAL", "ERROR") or is_blocking:
                blocking_count += 1
                reasons.append(f"Blocking {f.get('category', 'Issue')}: {f.get('message', '')} ({f.get('file', '')}:{f.get('line', 0)})")
            elif sev == "WARNING":
                warning_count += 1
            else:
                info_count += 1

        # Analyze failed critical acceptance criteria
        unsatisfied_critical_ac = [ac for ac in acceptance_results if not ac.get("is_satisfied", True) and ac.get("priority") == "HIGH"]
        if unsatisfied_critical_ac:
            blocking_count += len(unsatisfied_critical_ac)
            for ac in unsatisfied_critical_ac:
                reasons.append(f"Unsatisfied High-Priority Acceptance Criterion: {ac.get('description', '')}")

        # Deterministic Decision Matrix
        if blocking_count > 0:
            push_readiness = "DO_NOT_PUSH"
            # If critical security leaks or multiple blockers, risk is CRITICAL/HIGH
            has_critical = any(f.get("severity") == "CRITICAL" for f in findings)
            risk_level = "CRITICAL" if has_critical else "HIGH"
        elif warning_count > 0 or len(missing_tests) > 0:
            push_readiness = "MINOR_FIXES_REQUIRED"
            risk_level = "MEDIUM" if (warning_count > 2 or len(missing_tests) > 1) else "LOW"
            if warning_count > 0:
                reasons.append(f"{warning_count} quality/style warning(s) detected that should be reviewed.")
            if missing_tests:
                reasons.append(f"{len(missing_tests)} suggested test scenario(s) are missing.")
        else:
            push_readiness = "READY"
            risk_level = "LOW"
            reasons.append("All deterministic security rules, code quality checks, and standards passed.")

        # If acceptance criteria were missing, downgrade to LIMITED_REVIEW if otherwise ready
        if not has_criteria and push_readiness == "READY":
            push_readiness = "LIMITED_REVIEW"
            reasons.append("Review completed with LIMITED scope because no acceptance criteria were supplied.")

        return {
            "push_readiness": push_readiness,
            "risk_level": risk_level,
            "blocking_count": blocking_count,
            "warning_count": warning_count,
            "info_count": info_count,
            "reasons": reasons
        }
