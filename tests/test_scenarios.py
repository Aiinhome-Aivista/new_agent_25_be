import pytest
from app.agents.orchestrator import ReviewOrchestrator

SAMPLE_DIFF_CLEAN = """diff --git a/src/main/java/com/example/CustomerService.java b/src/main/java/com/example/CustomerService.java
new file mode 100644
index 0000000..1111111
--- /dev/null
+++ b/src/main/java/com/example/CustomerService.java
@@ -0,0 +1,10 @@
+package com.example;
+import org.springframework.stereotype.Service;
+
+@Service
+public class CustomerService {
+    public boolean isValidCustomer(String email) {
+        return email != null && email.contains("@");
+    }
+}
+"""

SAMPLE_DIFF_SECURITY = """diff --git a/src/main/java/com/example/CustomerRepository.java b/src/main/java/com/example/CustomerRepository.java
--- a/src/main/java/com/example/CustomerRepository.java
+++ b/src/main/java/com/example/CustomerRepository.java
@@ -10,4 +10,6 @@
+    public User findByEmailRaw(String email) {
+        return entityManager.createQuery("SELECT u FROM User u WHERE u.email = '" + email + "'").getSingleResult();
+    }
"""

SAMPLE_DIFF_SECRET = """diff --git a/src/main/resources/application.properties b/src/main/resources/application.properties
--- a/src/main/resources/application.properties
+++ b/src/main/resources/application.properties
@@ -1,2 +1,3 @@
+aws.access.key=AKIA1234567890EXAMPLE
"""

def test_scenario_1_clean_code():
    res = ReviewOrchestrator.run_review(
        git_diff=SAMPLE_DIFF_CLEAN,
        acceptance_criteria="Customer email validation logic",
        language="java",
        framework="spring-boot"
    )
    assert res["blockingIssues"] == 0
    assert res["pushReadiness"] in ("READY", "MINOR_FIXES_REQUIRED")

def test_scenario_3_security_vulnerability_blocks():
    res = ReviewOrchestrator.run_review(
        git_diff=SAMPLE_DIFF_SECURITY,
        acceptance_criteria="Find customer by email",
        language="java",
        framework="spring-boot"
    )
    assert res["pushReadiness"] == "DO_NOT_PUSH"
    assert res["blockingIssues"] > 0
    assert any(i["category"] == "Security" for i in res["issues"])

def test_scenario_secret_leak_blocks_and_redacts():
    res = ReviewOrchestrator.run_review(
        git_diff=SAMPLE_DIFF_SECRET,
        acceptance_criteria="Configure cloud storage",
        language="java",
        framework="spring-boot"
    )
    assert res["pushReadiness"] == "DO_NOT_PUSH"
    assert res["blockingIssues"] > 0
    # Ensure raw secret is never present in any issue message or evidence
    for issue in res["issues"]:
        assert "AKIA1234567890EXAMPLE" not in issue["message"]
        assert "AKIA1234567890EXAMPLE" not in issue["evidence"]
        assert "AKIA1234567890EXAMPLE" not in issue["suggestion"]

def test_scenario_7_no_diff_limited_review():
    res = ReviewOrchestrator.run_review(
        git_diff="",
        acceptance_criteria="Some task"
    )
    assert res["pushReadiness"] == "LIMITED_REVIEW"
