"""Pre-flight checks for LangSmith eval scripts."""
import os
import sys


def openai_key_configured() -> bool:
    """True when OPENAI_API_KEY looks like a real key (not empty or test placeholder)."""
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    return bool(key) and not key.startswith("sk-test")


def skip_if_no_openai(ci: bool = False) -> None:
    """Exit 0 with a message when OpenAI is not configured (avoids false 0.00 scores)."""
    if openai_key_configured():
        return
    print(
        "SKIP: OPENAI_API_KEY not configured — add secrets.OPENAI_API_KEY to run LLM evals"
    )
    if ci:
        print("  CI parse eval gate skipped until secret is set")
    sys.exit(0)
