import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Text, Boolean, TIMESTAMP, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.core.database import Base

def generate_uuid():
    return str(uuid.uuid4())

class ReviewSession(Base):
    __tablename__ = "review_sessions"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    repository_name = Column(String(255), nullable=False, default="workspace")
    branch = Column(String(255), default="main")
    commit_hash = Column(String(64), nullable=True)
    diff_hash = Column(String(64), nullable=False)
    author = Column(String(128), default="developer")
    status = Column(String(32), nullable=False, default="COMPLETED") # PENDING, IN_PROGRESS, COMPLETED, FAILED
    push_readiness = Column(String(32), nullable=False, default="READY") # READY, MINOR_FIXES_REQUIRED, DO_NOT_PUSH
    risk_level = Column(String(16), nullable=False, default="LOW") # LOW, MEDIUM, HIGH, CRITICAL
    confidence_score = Column(Float, default=1.0)
    blocking_issues_count = Column(Integer, default=0)
    warning_issues_count = Column(Integer, default=0)
    passed_checks_count = Column(Integer, default=0)
    missing_tests_count = Column(Integer, default=0)
    acceptance_criteria_raw = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    model_used = Column(String(64), default="gemini-3.7-flash")
    prompt_version = Column(String(32), default="v1.2.0")
    standards_version = Column(String(32), default="v2026.1")
    duration_ms = Column(Integer, default=0)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    findings = relationship("ReviewFinding", back_populates="session", cascade="all, delete-orphan")
    criteria_checks = relationship("AcceptanceCriteriaCheck", back_populates="session", cascade="all, delete-orphan")
    missing_tests = relationship("MissingTest", back_populates="session", cascade="all, delete-orphan")
    passed_checks = relationship("PassedCheck", back_populates="session", cascade="all, delete-orphan")
    audit_logs = relationship("ReviewAuditLog", back_populates="session", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "repository_name": self.repository_name,
            "branch": self.branch,
            "commit_hash": self.commit_hash,
            "diff_hash": self.diff_hash,
            "author": self.author,
            "status": self.status,
            "push_readiness": self.push_readiness,
            "risk_level": self.risk_level,
            "confidence_score": self.confidence_score,
            "blocking_issues_count": self.blocking_issues_count,
            "warning_issues_count": self.warning_issues_count,
            "passed_checks_count": self.passed_checks_count,
            "missing_tests_count": self.missing_tests_count,
            "acceptance_criteria_raw": self.acceptance_criteria_raw,
            "summary": self.summary,
            "model_used": self.model_used,
            "prompt_version": self.prompt_version,
            "standards_version": self.standards_version,
            "duration_ms": self.duration_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

class AcceptanceCriteriaCheck(Base):
    __tablename__ = "acceptance_criteria_checks"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    session_id = Column(String(64), ForeignKey("review_sessions.id", ondelete="CASCADE"), nullable=False)
    criterion_id = Column(String(32), nullable=False) # e.g. AC-001
    description = Column(Text, nullable=False)
    checkable_condition = Column(Text, nullable=False)
    priority = Column(String(16), default="HIGH")
    is_satisfied = Column(Boolean, default=False)
    evidence = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)

    session = relationship("ReviewSession", back_populates="criteria_checks")

    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "criterion_id": self.criterion_id,
            "description": self.description,
            "checkable_condition": self.checkable_condition,
            "priority": self.priority,
            "is_satisfied": self.is_satisfied,
            "evidence": self.evidence,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

class ReviewFinding(Base):
    __tablename__ = "review_findings"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    session_id = Column(String(64), ForeignKey("review_sessions.id", ondelete="CASCADE"), nullable=False)
    file_path = Column(String(512), nullable=False)
    line_number = Column(Integer, default=0)
    end_line_number = Column(Integer, default=0)
    severity = Column(String(16), nullable=False) # INFO, WARNING, ERROR, CRITICAL
    category = Column(String(64), nullable=False) # Security, Acceptance Criteria, Quality, Tests, Standards, Error Handling
    rule_id = Column(String(64), nullable=True)
    message = Column(Text, nullable=False)
    suggestion = Column(Text, nullable=False)
    evidence = Column(Text, nullable=True)
    is_blocking = Column(Boolean, default=False)
    source_tool = Column(String(64), default="agent")
    created_at = Column(TIMESTAMP, default=datetime.utcnow)

    session = relationship("ReviewSession", back_populates="findings")

    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "file": self.file_path,
            "file_path": self.file_path,
            "line": self.line_number,
            "line_number": self.line_number,
            "end_line_number": self.end_line_number,
            "severity": self.severity,
            "category": self.category,
            "rule_id": self.rule_id,
            "message": self.message,
            "suggestion": self.suggestion,
            "evidence": self.evidence,
            "is_blocking": self.is_blocking,
            "source_tool": self.source_tool,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

class MissingTest(Base):
    __tablename__ = "missing_tests"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    session_id = Column(String(64), ForeignKey("review_sessions.id", ondelete="CASCADE"), nullable=False)
    scenario_type = Column(String(32), nullable=False) # happy_path, negative_path, edge_case, regression
    target_file = Column(String(512), nullable=False)
    target_method = Column(String(255), nullable=True)
    description = Column(Text, nullable=False)
    suggested_test_code = Column(Text, nullable=True)
    priority = Column(String(16), default="MEDIUM")
    created_at = Column(TIMESTAMP, default=datetime.utcnow)

    session = relationship("ReviewSession", back_populates="missing_tests")

    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "scenario_type": self.scenario_type,
            "target_file": self.target_file,
            "target_method": self.target_method,
            "description": self.description,
            "suggested_test_code": self.suggested_test_code,
            "priority": self.priority
        }

class PassedCheck(Base):
    __tablename__ = "passed_checks"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    session_id = Column(String(64), ForeignKey("review_sessions.id", ondelete="CASCADE"), nullable=False)
    check_name = Column(String(255), nullable=False)
    category = Column(String(64), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)

    session = relationship("ReviewSession", back_populates="passed_checks")

    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "check_name": self.check_name,
            "category": self.category,
            "description": self.description
        }

class CodingStandard(Base):
    __tablename__ = "coding_standards"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    rule_code = Column(String(64), unique=True, nullable=False)
    language = Column(String(32), nullable=False)
    framework = Column(String(64), default="all")
    category = Column(String(64), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    bad_example = Column(Text, nullable=True)
    good_example = Column(Text, nullable=True)
    severity = Column(String(16), default="WARNING")
    is_blocking = Column(Boolean, default=False)
    version = Column(String(32), default="1.0.0")
    created_at = Column(TIMESTAMP, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "rule_code": self.rule_code,
            "language": self.language,
            "framework": self.framework,
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "bad_example": self.bad_example,
            "good_example": self.good_example,
            "severity": self.severity,
            "is_blocking": self.is_blocking,
            "version": self.version
        }

class ReviewAuditLog(Base):
    __tablename__ = "review_audit_logs"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    session_id = Column(String(64), ForeignKey("review_sessions.id", ondelete="CASCADE"), nullable=False)
    step_name = Column(String(64), nullable=False)
    agent_name = Column(String(64), nullable=False)
    event_type = Column(String(32), nullable=False)
    details = Column(JSON, nullable=True)
    duration_ms = Column(Integer, default=0)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)

    session = relationship("ReviewSession", back_populates="audit_logs")

    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "step_name": self.step_name,
            "agent_name": self.agent_name,
            "event_type": self.event_type,
            "details": self.details,
            "duration_ms": self.duration_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
