from typing import Dict, Any, List
from app.llm.provider import LLMProvider
from app.llm.prompts import SUMMARY_FEEDBACK_PROMPT

class FeedbackAgent:
    """Generates structured review summaries and formats inline code comments."""

    @classmethod
    def generate_summary(
        cls,
        diff_summary: str,
        blocking_count: int,
        warning_count: int,
        missing_tests_count: int,
        push_readiness: str
    ) -> str:
        if push_readiness == "DO_NOT_PUSH":
            return f"Review verdict is DO NOT PUSH. Found {blocking_count} blocking issue(s) that must be resolved prior to repository push."
        
        prompt = SUMMARY_FEEDBACK_PROMPT.format(
            diff_summary=diff_summary,
            blocking_count=blocking_count,
            warning_count=warning_count,
            missing_tests_count=missing_tests_count,
            push_readiness=push_readiness
        )
        resp = LLMProvider.generate(prompt)
        summary = resp.get("summary")
        
        if not summary or not isinstance(summary, str):
            if push_readiness == "READY":
                return "All quality gates and security checks passed cleanly. Changes are verified and ready for push."
            elif push_readiness == "MINOR_FIXES_REQUIRED":
                return f"Review completed with MINOR FIXES REQUIRED ({warning_count} warning(s), {missing_tests_count} missing test(s)). Please address recommendations before pushing."
            else:
                return f"Pre-push code review completed with status: {push_readiness}."
        
        return summary
