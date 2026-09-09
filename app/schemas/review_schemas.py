from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class AcceptanceCriterionInput(BaseModel):
    id: Optional[str] = None
    description: str
    checkableCondition: Optional[str] = None
    priority: Optional[str] = "HIGH"

class ReviewRequestSchema(BaseModel):
    repository_name: Optional[str] = "workspace"
    branch: Optional[str] = "main"
    git_diff: Optional[str] = ""
    acceptance_criteria: Optional[str] = ""
    language: Optional[str] = "java"
    framework: Optional[str] = "spring-boot"
    author: Optional[str] = "developer"
    rules_profile: Optional[str] = "default"

class GroundedIssueSchema(BaseModel):
    file: str
    line: int = 0
    end_line: Optional[int] = None
    severity: str = Field(..., pattern="^(INFO|WARNING|ERROR|CRITICAL)$")
    category: str
    rule_id: Optional[str] = None
    message: str
    suggestion: str
    evidence: str
    is_blocking: Optional[bool] = False
    source_tool: Optional[str] = "agent"

class MissingTestSchema(BaseModel):
    scenario_type: str # happy_path, negative_path, edge_case, regression
    target_file: str
    target_method: Optional[str] = None
    description: str
    suggested_test_code: Optional[str] = None
    priority: Optional[str] = "MEDIUM"

class PassedCheckSchema(BaseModel):
    check_name: str
    category: str
    description: Optional[str] = None

class AcceptanceCriteriaCheckResult(BaseModel):
    criterion_id: str
    description: str
    checkable_condition: str
    priority: str = "HIGH"
    is_satisfied: bool
    evidence: Optional[str] = None

class ReviewMetadataSchema(BaseModel):
    sessionId: str
    diffHash: str
    model: str
    promptVersion: str
    standardsVersion: str
    durationMs: int = 0
    timestamp: str

class ReviewResponseSchema(BaseModel):
    summary: str
    pushReadiness: str = Field(..., pattern="^(READY|MINOR_FIXES_REQUIRED|DO_NOT_PUSH|LIMITED_REVIEW)$")
    riskLevel: str = Field(..., pattern="^(LOW|MEDIUM|HIGH|CRITICAL|UNKNOWN)$")
    blockingIssues: int = 0
    warningIssues: int = 0
    passedChecksCount: int = 0
    missingTestsCount: int = 0
    issues: List[GroundedIssueSchema] = []
    missingTests: List[MissingTestSchema] = []
    passedChecks: List[PassedCheckSchema] = []
    acceptanceCriteriaResults: List[AcceptanceCriteriaCheckResult] = []
    reviewMetadata: ReviewMetadataSchema
