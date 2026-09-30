import sys
import os
sys.path.append(os.path.abspath("d:/agent_25/backend"))
from app.agents.orchestrator import ReviewOrchestrator

diff = """
+++ b/test.java
@@ -0,0 +1,10 @@
+public class Test {
+    public void test() {
+        String s = "";
+        switch("A") {
+            case "A": s = "1"; break;
+        }
+    }
+}
"""
result = ReviewOrchestrator.run_review(
    git_diff=diff,
    language="java",
    language_version="17",
    repository_name="test"
)
print("PUSH VERDICT:", result.get("pushReadiness"))
for issue in result.get("issues", []):
    print("-", issue.get("rule_id"), ":", issue.get("message"))
