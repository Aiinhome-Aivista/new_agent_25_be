import time
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
from app.core.logging_config import logger
from app.core.config import config
from app.core import database as db_core
from app.models.entities import ReviewSession, AcceptanceCriteriaCheck, ReviewFinding, MissingTest, PassedCheck, ReviewAuditLog, ReusableComponent
from app.agents.acceptance_agent import AcceptanceCriteriaAgent
from app.agents.diff_context_agent import DiffContextAgent
from app.agents.quality_agent import CodeQualityAgent
from app.agents.test_coverage_agent import TestCoverageAgent
from app.agents.push_readiness_engine import PushReadinessEngine
from app.agents.feedback_agent import FeedbackAgent
from app.agents.reusable_code_agent import ReusableCodeAgent

class ReviewOrchestrator:
    """Stateful Plan-and-Execute Orchestrator managing end-to-end multi-agent pre-push review pipeline."""

    @classmethod
    def run_review(
        cls,
        git_diff: str = "",
        acceptance_criteria: str = "",
        repository_name: str = "workspace",
        branch: str = "main",
        language: Optional[str] = None,
        framework: Optional[str] = None,
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

        log_step("ReviewSession", "Orchestrator", "AGENT_START", {"repository": repository_name, "branch": branch})

        # Initialize defaults for safe persistence in case of early exit or failure
        diff_result = {"diff_hash": "", "has_diff": False, "file_count": 0, "total_added_lines": 0, "changed_files": [], "raw_diff": ""}
        ac_result = {"criteria": [], "has_criteria": False}
        quality_result = {"findings": [], "passed_checks": []}
        test_result = {"missing_tests": []}
        ac_checks = []
        readiness_eval = {"push_readiness": "FAILED", "risk_level": "UNKNOWN", "blocking_count": 0, "warning_count": 0}
        summary = "Review failed due to an internal error."
        session_status = "FAILED"
        model_name = config.GEMINI_MODEL if config.MODE.lower() == "gemini" else (config.MODEL_NAME or config.MISTRAL_LOCAL_MODEL)
        total_duration_ms = 0

        try:
            # Step 1: Acceptance Criteria Parsing
            t0 = time.time()
            log_step("ParseAcceptanceCriteria", "AcceptanceCriteriaAgent", "AGENT_START", {"raw_criteria_length": len(acceptance_criteria)})
            try:
                ac_result = AcceptanceCriteriaAgent.execute(acceptance_criteria)
                log_step("ParseAcceptanceCriteria", "AcceptanceCriteriaAgent", "AGENT_END", {"criteria_count": len(ac_result["criteria"])}, int((time.time() - t0)*1000))
            except Exception as e:
                log_step("ParseAcceptanceCriteria", "AcceptanceCriteriaAgent", "ERROR", {"error": str(e)}, int((time.time() - t0)*1000))
                raise

            # Step 2: Diff & Code Context Extraction
            t0 = time.time()
            log_step("CollectDiffContext", "DiffContextAgent", "AGENT_START", {"git_diff_length": len(git_diff)})
            try:
                diff_result = DiffContextAgent.execute(git_diff)
                log_step("CollectDiffContext", "DiffContextAgent", "AGENT_END", {"diff_hash": diff_result["diff_hash"], "files_count": diff_result["file_count"]}, int((time.time() - t0)*1000))
            except Exception as e:
                log_step("CollectDiffContext", "DiffContextAgent", "ERROR", {"error": str(e)}, int((time.time() - t0)*1000))
                raise

            if not diff_result["has_diff"]:
                summary = "No Git diff detected in review request. Please stage or modify code files before running review."
                readiness_eval["push_readiness"] = "LIMITED_REVIEW"
                session_status = "COMPLETED"
                log_step("ReviewSession", "Orchestrator", "AGENT_END", {"status": "NO_DIFF"}, int((time.time() - start_time)*1000))
                return

            # Auto-detect language and framework from diff if not provided
            if not language:
                py_count = sum(1 for f in diff_result["changed_files"] if (f.new_path or f.old_path or "").endswith(".py"))
                ts_count = sum(1 for f in diff_result["changed_files"] if (f.new_path or f.old_path or "").endswith((".ts", ".tsx", ".js", ".jsx")))
                java_count = sum(1 for f in diff_result["changed_files"] if (f.new_path or f.old_path or "").endswith(".java"))
                go_count = sum(1 for f in diff_result["changed_files"] if (f.new_path or f.old_path or "").endswith(".go"))
                
                if py_count > java_count and py_count > ts_count and py_count > go_count:
                    language = "python"
                    framework = framework or "flask"
                elif ts_count > java_count and ts_count > py_count and ts_count > go_count:
                    language = "typescript"
                    framework = framework or "react"
                elif go_count > java_count and go_count > py_count and go_count > ts_count:
                    language = "golang"
                    framework = framework or "standard"
                else:
                    language = "java"
                    framework = framework or "spring-boot"
            else:
                framework = framework or "standard"

            # Step 2a: Detect Reusable Components
            t0 = time.time()
            log_step("DetectReusableComponents", "ReusableCodeAgent", "AGENT_START", {"language": language, "framework": framework})
            try:
                reusable_components = ReusableCodeAgent.execute(
                    raw_diff=diff_result["raw_diff"],
                    language=language,
                    framework=framework
                )
                log_step("DetectReusableComponents", "ReusableCodeAgent", "AGENT_END", {"count": len(reusable_components)}, int((time.time() - t0)*1000))
            except Exception as e:
                log_step("DetectReusableComponents", "ReusableCodeAgent", "ERROR", {"error": str(e)}, int((time.time() - t0)*1000))
                reusable_components = []

            # Step 3: Code Quality & Security Evaluation
            t0 = time.time()
            log_step("EvaluateCodeQuality", "CodeQualityAgent", "AGENT_START", {"language": language, "framework": framework})
            try:
                quality_result = CodeQualityAgent.execute(
                    changed_files=diff_result["changed_files"],
                    raw_diff=diff_result["raw_diff"],
                    acceptance_criteria=ac_result["criteria"],
                    language=language,
                    framework=framework
                )
                log_step("EvaluateCodeQuality", "CodeQualityAgent", "AGENT_END", {"findings_count": len(quality_result["findings"])}, int((time.time() - t0)*1000))
            except Exception as e:
                log_step("EvaluateCodeQuality", "CodeQualityAgent", "ERROR", {"error": str(e)}, int((time.time() - t0)*1000))
                raise

            # Step 4: Missing Tests Coverage Analysis
            t0 = time.time()
            log_step("AnalyzeTestCoverage", "TestCoverageAgent", "AGENT_START", {})
            try:
                test_result = TestCoverageAgent.execute(
                    changed_files=diff_result["changed_files"],
                    raw_diff=diff_result["raw_diff"],
                    acceptance_criteria=ac_result["criteria"],
                    language=language,
                    framework=framework
                )
                log_step("AnalyzeTestCoverage", "TestCoverageAgent", "AGENT_END", {"missing_count": len(test_result["missing_tests"])}, int((time.time() - t0)*1000))
            except Exception as e:
                log_step("AnalyzeTestCoverage", "TestCoverageAgent", "ERROR", {"error": str(e)}, int((time.time() - t0)*1000))
                raise

            # Step 5: Acceptance Criteria Satisfaction Verification
            t0 = time.time()
            log_step("VerifyAcceptanceCriteria", "AcceptanceCriteriaAgent", "AGENT_START", {})
            try:
                verified_criteria = AcceptanceCriteriaAgent.verify_criteria_against_diff(
                    criteria=ac_result["criteria"],
                    raw_diff=diff_result["raw_diff"]
                )
                
                ac_checks = []
                for ac in ac_result["criteria"]:
                    verification = next((vc for vc in verified_criteria if vc.get("criterion_id") == ac["id"]), None)
                    
                    if verification:
                        is_satisfied = verification.get("is_satisfied", False)
                        evidence = verification.get("evidence", "")
                        if not is_satisfied and verification.get("missing_details"):
                            evidence += f" Missing: {verification.get('missing_details')}"
                    else:
                        is_satisfied = False
                        evidence = "No verification data generated."
                        
                    ac_checks.append({
                        "criterion_id": ac["id"],
                        "description": ac["description"],
                        "checkable_condition": ac["checkableCondition"],
                        "priority": ac["priority"],
                        "is_satisfied": is_satisfied,
                        "evidence": evidence
                    })
                
                log_step("VerifyAcceptanceCriteria", "AcceptanceCriteriaAgent", "AGENT_END", {"checks_count": len(ac_checks)}, int((time.time() - t0)*1000))
            except Exception as e:
                log_step("VerifyAcceptanceCriteria", "AcceptanceCriteriaAgent", "ERROR", {"error": str(e)}, int((time.time() - t0)*1000))
                raise

            # Step 6: Deterministic Push Readiness Engine Evaluation
            t0 = time.time()
            log_step("EvaluatePushReadiness", "PushReadinessEngine", "AGENT_START", {})
            try:
                readiness_eval = PushReadinessEngine.evaluate(
                    findings=quality_result["findings"],
                    missing_tests=[],
                    acceptance_results=ac_checks,
                    has_diff=diff_result["has_diff"],
                    has_criteria=ac_result["has_criteria"]
                )
                log_step("EvaluatePushReadiness", "PushReadinessEngine", "AGENT_END", readiness_eval, int((time.time() - t0)*1000))
            except Exception as e:
                log_step("EvaluatePushReadiness", "PushReadinessEngine", "ERROR", {"error": str(e)}, int((time.time() - t0)*1000))
                raise

            # Step 7: Feedback & Summary Generation
            t0 = time.time()
            log_step("GenerateFeedback", "FeedbackAgent", "AGENT_START", {})
            try:
                summary = FeedbackAgent.generate_summary(
                    diff_summary=f"Changed {diff_result['file_count']} file(s) with {diff_result['total_added_lines']} line(s) added/modified.",
                    blocking_count=readiness_eval["blocking_count"],
                    warning_count=readiness_eval["warning_count"],
                    missing_tests_count=0,
                    push_readiness=readiness_eval["push_readiness"]
                )
                log_step("GenerateFeedback", "FeedbackAgent", "AGENT_END", {"summary_length": len(summary)}, int((time.time() - t0)*1000))
            except Exception as e:
                log_step("GenerateFeedback", "FeedbackAgent", "ERROR", {"error": str(e)}, int((time.time() - t0)*1000))
                raise

            session_status = "COMPLETED"
            log_step("ReviewSession", "Orchestrator", "AGENT_END", {"status": "SUCCESS"}, int((time.time() - start_time)*1000))

        except Exception as main_e:
            log_step("ReviewSession", "Orchestrator", "ERROR", {"error": str(main_e)}, int((time.time() - start_time)*1000))
            logger.error(f"Review session failed: {main_e}", exc_info=True)
            exception_to_raise = main_e
        else:
            exception_to_raise = None
        finally:
            total_duration_ms = int((time.time() - start_time) * 1000)
            # Step 8: Database Persistence
            try:
                if db_core.SessionLocal:
                    db = db_core.SessionLocal()
                    session_entity = ReviewSession(
                        id=session_id,
                        repository_name=repository_name,
                        branch=branch,
                        language=language,
                        framework=framework,
                        diff_hash=diff_result["diff_hash"],
                        author=author,
                        status=session_status,
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
                            fix_code=f.get("fix_code"),
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

                    # Add Reusable Components
                    for rc in reusable_components:
                        db.add(ReusableComponent(
                            id=str(uuid.uuid4()),
                            session_id=session_id,
                            name=rc.get("name", "Unknown"),
                            component_type=rc.get("component_type", "FUNCTION"),
                            description=rc.get("description", ""),
                            file_path=rc.get("file_path", ""),
                            snippet=rc.get("snippet", "")
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
                else:
                    logger.error("CRITICAL: Database persistence skipped! db_core.SessionLocal is None. This means the backend failed to connect to the database during startup.")
            except Exception as db_err:
                logger.error(f"Failed to persist review session to database: {db_err}")

            if exception_to_raise:
                raise exception_to_raise

            return {
                "session": {
                    "id": session_id,
                    "repository_name": repository_name,
                    "branch": branch,
                    "language": language,
                    "author": author,
                    "status": session_status
                },
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
                "reusableComponents": reusable_components,
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

        # Auto-detect language and framework from diff if not provided
        if not language:
            py_count = sum(1 for f in diff_result["changed_files"] if (f.new_path or f.old_path or "").endswith(".py"))
            ts_count = sum(1 for f in diff_result["changed_files"] if (f.new_path or f.old_path or "").endswith((".ts", ".tsx", ".js", ".jsx")))
            java_count = sum(1 for f in diff_result["changed_files"] if (f.new_path or f.old_path or "").endswith(".java"))
            go_count = sum(1 for f in diff_result["changed_files"] if (f.new_path or f.old_path or "").endswith(".go"))
            
            if py_count > java_count and py_count > ts_count and py_count > go_count:
                language = "python"
                framework = framework or "flask"
            elif ts_count > java_count and ts_count > py_count and ts_count > go_count:
                language = "typescript"
                framework = framework or "react"
            elif go_count > java_count and go_count > py_count and go_count > ts_count:
                language = "golang"
                framework = framework or "standard"
            else:
                language = "java"
                framework = framework or "spring-boot"
        else:
            framework = framework or "standard"

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

        # Step 4: Missing Tests Coverage Analysis
        t0 = time.time()
        test_result = TestCoverageAgent.execute(
            changed_files=diff_result["changed_files"],
            raw_diff=diff_result["raw_diff"],
            acceptance_criteria=ac_result["criteria"],
            language=language,
            framework=framework
        )
        log_step("AnalyzeTestCoverage", "TestCoverageAgent", "AGENT_END", {"missing_count": len(test_result["missing_tests"])}, int((time.time() - t0)*1000))

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
                        fix_code=f.get("fix_code"),
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
