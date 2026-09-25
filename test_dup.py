import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.rag.codebase_store import codebase_store
from app.agents.duplicate_code_agent import DuplicateCodeAgent
from app.tools.git_tool import GitTool

# 1. Read UserService.java and index it
user_service_path = r"d:\agent\pwc\agent25\test\spring-boot-poc\src\main\java\com\example\crudpoc\service\UserService.java"
with open(user_service_path, "r", encoding="utf-8") as f:
    user_service_content = f.read()

indexed = codebase_store.index_file("src/main/java/com/example/crudpoc/service/UserService.java", user_service_content, "java")
print(f"Indexed UserService chunks: {indexed}")

# 2. Read UserProfileService.java and simulate git diff
user_profile_path = r"d:\agent\pwc\agent25\test\spring-boot-poc\src\main\java\com\example\crudpoc\service\UserProfileService.java"
with open(user_profile_path, "r", encoding="utf-8") as f:
    user_profile_content = f.read()

# Make synthetic diff
diff_lines = ["diff --git a/src/main/java/com/example/crudpoc/service/UserProfileService.java b/src/main/java/com/example/crudpoc/service/UserProfileService.java",
              "new file mode 100644",
              "--- /dev/null",
              "+++ b/src/main/java/com/example/crudpoc/service/UserProfileService.java",
              "@@ -0,0 +1,61 @@"]
for line in user_profile_content.splitlines():
    diff_lines.append("+" + line)

raw_diff = "\n".join(diff_lines)
changed_files = GitTool.parse_diff(raw_diff)
print(f"Parsed changed files: {len(changed_files)}")

# 3. Run DuplicateCodeAgent
res = DuplicateCodeAgent.execute(changed_files, language="java")
print(f"Duplicate result: {res}")
