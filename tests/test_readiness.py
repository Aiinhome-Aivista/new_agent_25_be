import pytest
from app.agents.push_readiness_engine import PushReadinessEngine

def test_push_readiness_clean_code():
    res = PushReadinessEngine.evaluate(
        findings=[],
        missing_tests=[],
        acceptance_results=[{"criterion_id": "AC-1", "is_satisfied": True, "priority": "HIGH"}],
        has_diff=True,
        has_criteria=True
    )
    assert res["push_readiness"] == "READY"
    assert res["risk_level"] == "LOW"
    assert res["blocking_count"] == 0

def test_push_readiness_critical_security_blocks():
    findings = [
        {"severity": "CRITICAL", "category": "Security", "message": "SQL Injection found", "file": "UserRepo.java", "line": 15, "is_blocking": True}
    ]
    res = PushReadinessEngine.evaluate(
        findings=findings,
        missing_tests=[],
        acceptance_results=[],
        has_diff=True,
        has_criteria=True
    )
    assert res["push_readiness"] == "DO_NOT_PUSH"
    assert res["risk_level"] == "CRITICAL"
    assert res["blocking_count"] == 1

def test_push_readiness_minor_warnings():
    findings = [
        {"severity": "WARNING", "category": "Quality", "message": "Missing Javadoc comment", "file": "App.java", "line": 10, "is_blocking": False}
    ]
    res = PushReadinessEngine.evaluate(
        findings=findings,
        missing_tests=[],
        acceptance_results=[],
        has_diff=True,
        has_criteria=True
    )
    assert res["push_readiness"] == "MINOR_FIXES_REQUIRED"
    assert res["blocking_count"] == 0
    assert res["warning_count"] == 1

def test_push_readiness_failed_high_priority_ac_blocks():
    res = PushReadinessEngine.evaluate(
        findings=[],
        missing_tests=[],
        acceptance_results=[{"criterion_id": "AC-1", "is_satisfied": False, "priority": "HIGH", "description": "Email validation"}],
        has_diff=True,
        has_criteria=True
    )
    assert res["push_readiness"] == "DO_NOT_PUSH"
    assert res["blocking_count"] >= 1
