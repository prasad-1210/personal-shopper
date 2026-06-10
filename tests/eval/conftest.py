"""
Common fixtures for LangSmith eval scripts.

All eval scripts use mock tools so they:
  - Don't require real API keys in CI
  - Don't burn Edamam/Kroger API quota
  - Run in ~10s per dataset instead of 60s+
"""
import os

os.environ.setdefault("USE_MOCK_TOOLS", "true")
os.environ.setdefault("LANGSMITH_TRACING", "true")
os.environ.setdefault(
    "OPENAI_API_KEY", os.environ.get("OPENAI_API_KEY", "sk-test-fake")
)
