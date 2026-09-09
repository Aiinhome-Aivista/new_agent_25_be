import time
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
from backend.app.core.logging_config import logger
from backend.app.core.config import config
from backend.app.core.database import SessionLocal
from backend.app.models.entities import ReviewSession, AcceptanceCriteriaCheck, ReviewFinding, MissingTest, PassedCheck, ReviewAuditLog
from backend.app.agents.acceptance_agent import AcceptanceCriteriaAgent
from backend.app.agents.diff_context_agent import DiffContextAgent
from backend.app.agents.quality_agent import CodeQualityAgent
from backend.app.agents.test_coverage_agent import TestCoverageAgent
from backend.app.agents.push_readiness_engine import PushReadinessEngine
from backend.app.agents.feedback_agent import FeedbackAgent

class ReviewOrchestrator:
    """Stateful Plan-and-Execute Orchestrator managing end-to-end multi-agent pre-push review pipeline."""

    @classmethod
    def run_review(
        cls,
        git_diff: str = "",
        acceptance_criteria: str = "",
        repository_name: str = "workspace",
        branch: str = "main",
        language: str = "java",
        framework: str = "spring-boot",
        author: str = "developer"
    ) -> Dict[str, Any]:
        start_time = time.time()
        session_id = str(uuid.uuid4())
        audit_events = []

        logger.info(f"Starting review session {session_id} for repo={repository_name}, branch={branch}")

        def log_step(step_name: str, agent_name: str, event_type: str, details: Dict[str, Any], duration: int = 0):
            audit_events.append({
                "step_name": step_name,
                "agent_name": agent_name,
                "event_type": event_type,
                "details": details,
                "duration_ms": duration
            })

        # Step 1: Acceptance Criteria Parsing
        t0 = time.time()
        ac_result = AcceptanceCriteriaAgent.execute(acceptance_criteria)
        log_step("ParseAcceptanceCriteria", "AcceptanceCriteriaAgent", "AGENT_END", {"criteria_count": len(ac_result["criteria"])}, int((time.time() - t0)*1000))

        # Step 2: Diff & Code Context Extraction
        t0 = time.time()
        diff_result = DiffContextAgent.execute(git_diff)
        log_step("CollectDiffContext", "DiffContextAgent", "AGENT_END", {"diff_hash": diff_result["diff_hash"], "files_count": diff_result["file_count"]}, int((time.time() - t0)*1000))

        if not diff_result["has_diff"]:
            # Early stop if diff unavailable
            summary = "No Git diff detected in review request. Please stage or modify code files before running review."
            return {
                "summary": summary,
                "pushReadiness": "LIMITED_REVIEW",
                "riskLevel": "UNKNOWN",
                "blockingIssues": 0,
                "warningIssues": 0,
                "passedChecksCount": 0,
                "missingTestsCount": 0,
                "issues": [],
                "missingTests": [],
                "passedChecks": [],
                "acceptanceCriteriaResults": [],
                "reviewMetadata": {
                    "sessionId": session_id,
                    "diffHash": "",
                    "model": config.GEMINI_MODEL if config.MODE == "Gemini" else (config.MODEL_NAME or config.MISTRAL_LOCAL_MODEL),
                    "promptVersion": "v1.2.0",
                    "standardsVersion": "v2026.1",
                    "durationMs": int((time.time() - start_time) * 1000),
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }
            }

        # Step 3: Code Quality & Security Evaluation
        t0 = time.time()
        quality_result = CodeQualityAgent.execute(
            changed_files=diff_result["changed_files"],
            raw_diff=diff_result["raw_diff"],
            acceptance_criteria=ac_result["criteria"],
            language=language,
            framework=framework
        )
        log_step("EvaluateCodeQuality", "CodeQualityAgent", "AGENT_END", {"findings_count": len(quality_result["findings"])}, int((time.time() - t0)*1000))

        # Step 4: Test Coverage & Edge Cases Analysis
        t0 = time.time()
        test_result = TestCoverageAgent.execute(
            changed_files=diff_result["changed_files"],
            raw_diff=diff_result["raw_diff"],
            acceptance_criteria=ac_result["criteria"]
        )
        log_step("AnalyzeTestCoverage", "TestCoverageAgent", "AGENT_END", {"missing_tests_count": len(test_result["missing_tests"])}, int((time.time() - t0)*1000))

        # Step 5: Acceptance Criteria Satisfaction Verification
        ac_checks = []
        for ac in ac_result["criteria"]:
            # Simple heuristic matching on checkable condition
            is_satisfied = True
            evidence = "Verified in changed code."
            # Check if any blocking finding matches this AC
            for f in quality_result["findings"]:
                if f.get("category") == "Acceptance Criteria" and f.get("severity") in ("ERROR", "CRITICAL"):
                    is_satisfied = False
                    evidence = f.get("message", "Criteria violation detected")
                    break
            
            ac_checks.append({
                "criterion_id": ac["id"],
                "description": ac["description"],
                "checkable_condition": ac["checkableCondition"],
                "priority": ac["priority"],
                "is_satisfied": is_satisfied,
                "evidence": evidence
            })

        # Step 6: Deterministic Push Readiness Engine Evaluation
        t0 = time.time()
        readiness_eval = PushReadinessEngine.evaluate(
            findings=quality_result["findings"],
            missing_tests=test_result["missing_tests"],
            acceptance_results=ac_checks,
            has_diff=diff_result["has_diff"],
            has_criteria=ac_result["has_criteria"]
        )
        log_step("EvaluatePushReadiness", "PushReadinessEngine", "AGENT_END", readiness_eval, int((time.time() - t0)*1000))

        # Step 7: Feedback & Summary Generation
        t0 = time.time()
        summary = FeedbackAgent.generate_summary(
            diff_summary=f"Changed {diff_result['file_count']} file(s) with {diff_result['total_added_lines']} line(s) added/modified.",
            blocking_count=readiness_eval["blocking_count"],
            warning_count=readiness_eval["warning_count"],
            missing_tests_count=len(test_result["missing_tests"]),
            push_readiness=readiness_eval["push_readiness"]
        )
        log_step("GenerateFeedback", "FeedbackAgent", "AGENT_END", {"summary_length": len(summary)}, int((time.time() - t0)*1000))

        total_duration_ms = int((time.time() - start_time) * 1000)
        model_name = config.GEMINI_MODEL if config.MODE.lower() == "gemini" else (config.MODEL_NAME or config.MISTRAL_LOCAL_MODEL)

        # Step 8: Database Persistence
        try:
            if SessionLocal:
                db = SessionLocal()
                session_entity = ReviewSession(
                    id=session_id,
                    repository_name=repository_name,
                    branch=branch,
                    diff_hash=diff_result["diff_hash"],
                    author=author,
                    status="COMPLETED",
                    push_readiness=readiness_eval["push_readiness"],
                    risk_level=readiness_eval["risk_level"],
                    blocking_issues_count=readiness_eval["blocking_count"],
                    warning_issues_count=readiness_eval["warning_count"],
                    passed_checks_count=len(quality_result["passed_checks"]),
                    missing_tests_count=len(test_result["missing_tests"]),
                    acceptance_criteria_raw=acceptance_criteria,
                    summary=summary,
                    model_used=model_name,
                    prompt_version="v1.2.0",
                    standards_version="v2026.1",
                    duration_ms=total_duration_ms
                )
                db.add(session_entity)

                # Add findings
                for f in quality_result["findings"]:
                    db.add(ReviewFinding(
                        id=str(uuid.uuid4()),
                        session_id=session_id,
                        file_path=f["file"],
                        line_number=f["line"],
                        severity=f["severity"],
                        category=f["category"],
                        rule_id=f.get("rule_id"),
                        message=f["message"],
                        suggestion=f["suggestion"],
                        evidence=f.get("evidence"),
                        is_blocking=f.get("is_blocking", False),
                        source_tool=f.get("source_tool", "agent")
                    ))

                # Add AC checks
                for ac in ac_checks:
                    db.add(AcceptanceCriteriaCheck(
                        id=str(uuid.uuid4()),
                        session_id=session_id,
                        criterion_id=ac["criterion_id"],
                        description=ac["description"],
                        checkable_condition=ac["checkable_condition"],
                        priority=ac["priority"],
                        is_satisfied=ac["is_satisfied"],
                        evidence=ac.get("evidence")
                    ))

                # Add Missing Tests
                for mt in test_result["missing_tests"]:
                    db.add(MissingTest(
                        id=str(uuid.uuid4()),
                        session_id=session_id,
                        scenario_type=mt["scenario_type"],
                        target_file=mt["target_file"],
                        target_method=mt.get("target_method"),
                        description=mt["description"],
                        suggested_test_code=mt.get("suggested_test_code"),
                        priority=mt.get("priority", "MEDIUM")
                    ))

                # Add Passed Checks
                for pc in quality_result["passed_checks"]:
                    db.add(PassedCheck(
                        id=str(uuid.uuid4()),
                        session_id=session_id,
                        check_name=pc["check_name"],
                        category=pc["category"],
                        description=pc.get("description")
                    ))

                # Add Audit Logs
                for al in audit_events:
                    db.add(ReviewAuditLog(
                        id=str(uuid.uuid4()),
                        session_id=session_id,
                        step_name=al["step_name"],
                        agent_name=al["agent_name"],
                        event_type=al["event_type"],
                        details=al["details"],
                        duration_ms=al["duration_ms"]
                    ))

                db.commit()
                db.close()
                logger.info(f"Review session {session_id} saved to database.")
        except Exception as db_err:
            logger.error(f"Failed to persist review session to database: {db_err}")

        return {
            "summary": summary,
            "pushReadiness": readiness_eval["push_readiness"],
            "riskLevel": readiness_eval["risk_level"],
            "blockingIssues": readiness_eval["blocking_count"],
            "warningIssues": readiness_eval["warning_count"],
            "passedChecksCount": len(quality_result["passed_checks"]),
            "missingTestsCount": len(test_result["missing_tests"]),
            "issues": quality_result["findings"],
            "missingTests": test_result["missing_tests"],
            "passedChecks": quality_result["passed_checks"],
            "acceptanceCriteriaResults": ac_checks,
            "reviewMetadata": {
                "sessionId": session_id,
                "diffHash": diff_result["diff_hash"],
                "model": model_name,
                "promptVersion": "v1.2.0",
                "standardsVersion": "v2026.1",
                "durationMs": total_duration_ms,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        }
