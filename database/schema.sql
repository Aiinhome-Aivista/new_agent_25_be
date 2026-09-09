-- AI Code Review Agent Database Schema
-- Target: MySQL 8.0+

CREATE DATABASE IF NOT EXISTS ai_code_review CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE ai_code_review;

-- Review Sessions table
CREATE TABLE IF NOT EXISTS review_sessions (
    id VARCHAR(64) PRIMARY KEY,
    repository_name VARCHAR(255) NOT NULL,
    branch VARCHAR(255) DEFAULT 'main',
    commit_hash VARCHAR(64),
    diff_hash VARCHAR(64) NOT NULL,
    author VARCHAR(128) DEFAULT 'developer',
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    push_readiness VARCHAR(32) NOT NULL DEFAULT 'PENDING', -- READY, MINOR_FIXES_REQUIRED, DO_NOT_PUSH
    risk_level VARCHAR(16) NOT NULL DEFAULT 'UNKNOWN',    -- LOW, MEDIUM, HIGH, CRITICAL
    confidence_score FLOAT DEFAULT 1.0,
    blocking_issues_count INT DEFAULT 0,
    warning_issues_count INT DEFAULT 0,
    passed_checks_count INT DEFAULT 0,
    missing_tests_count INT DEFAULT 0,
    acceptance_criteria_raw TEXT,
    summary TEXT,
    model_used VARCHAR(64),
    prompt_version VARCHAR(32),
    standards_version VARCHAR(32),
    duration_ms INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_repo_branch (repository_name, branch),
    INDEX idx_created (created_at),
    INDEX idx_readiness (push_readiness)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Acceptance Criteria check records
CREATE TABLE IF NOT EXISTS acceptance_criteria_checks (
    id VARCHAR(64) PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL,
    criterion_id VARCHAR(32) NOT NULL,
    description TEXT NOT NULL,
    checkable_condition TEXT NOT NULL,
    priority VARCHAR(16) DEFAULT 'HIGH', -- HIGH, MEDIUM, LOW
    is_satisfied BOOLEAN NOT NULL DEFAULT FALSE,
    evidence TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES review_sessions(id) ON DELETE CASCADE,
    INDEX idx_session_ac (session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Review Findings / Issues
CREATE TABLE IF NOT EXISTS review_findings (
    id VARCHAR(64) PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL,
    file_path VARCHAR(512) NOT NULL,
    line_number INT DEFAULT 0,
    end_line_number INT DEFAULT 0,
    severity VARCHAR(16) NOT NULL, -- INFO, WARNING, ERROR, CRITICAL
    category VARCHAR(64) NOT NULL, -- Security, Acceptance Criteria, Quality, Tests, Standards, Error Handling
    rule_id VARCHAR(64),
    message TEXT NOT NULL,
    suggestion TEXT NOT NULL,
    evidence TEXT,
    is_blocking BOOLEAN DEFAULT FALSE,
    source_tool VARCHAR(64) DEFAULT 'agent', -- deterministic_sast, secret_scanner, ai_agent, linter
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES review_sessions(id) ON DELETE CASCADE,
    INDEX idx_session_severity (session_id, severity),
    INDEX idx_file (file_path(255))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Missing Test Scenarios
CREATE TABLE IF NOT EXISTS missing_tests (
    id VARCHAR(64) PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL,
    scenario_type VARCHAR(32) NOT NULL, -- happy_path, negative_path, edge_case, regression
    target_file VARCHAR(512) NOT NULL,
    target_method VARCHAR(255),
    description TEXT NOT NULL,
    suggested_test_code TEXT,
    priority VARCHAR(16) DEFAULT 'MEDIUM',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES review_sessions(id) ON DELETE CASCADE,
    INDEX idx_session_tests (session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Passed Checks
CREATE TABLE IF NOT EXISTS passed_checks (
    id VARCHAR(64) PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL,
    check_name VARCHAR(255) NOT NULL,
    category VARCHAR(64) NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES review_sessions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Coding Standards and RAG Knowledge Items
CREATE TABLE IF NOT EXISTS coding_standards (
    id VARCHAR(64) PRIMARY KEY,
    rule_code VARCHAR(64) UNIQUE NOT NULL,
    language VARCHAR(32) NOT NULL, -- java, python, javascript, typescript, general
    framework VARCHAR(64) DEFAULT 'all', -- spring-boot, flask, react, general
    category VARCHAR(64) NOT NULL, -- security, quality, architecture, testing, error-handling
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    bad_example TEXT,
    good_example TEXT,
    severity VARCHAR(16) DEFAULT 'WARNING',
    is_blocking BOOLEAN DEFAULT FALSE,
    version VARCHAR(32) DEFAULT '1.0.0',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_lang_fw (language, framework),
    INDEX idx_category (category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Immutable Audit & Trace Logs
CREATE TABLE IF NOT EXISTS review_audit_logs (
    id VARCHAR(64) PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL,
    step_name VARCHAR(64) NOT NULL,
    agent_name VARCHAR(64) NOT NULL,
    event_type VARCHAR(32) NOT NULL, -- AGENT_START, AGENT_END, TOOL_EXEC, GUARDRAIL_TRIGGER, ERROR
    details JSON,
    duration_ms INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES review_sessions(id) ON DELETE CASCADE,
    INDEX idx_audit_session (session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
