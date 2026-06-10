"""Load version-controlled LLM prompt templates from ``shared/prompts/``.

Prompt text is cached in-process after first read. Restart agents to pick up
``.md`` file edits (hot-reload is not implemented).
"""
from __future__ import annotations

from pathlib import Path

from langchain_core.prompts import ChatPromptTemplate

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
_cache: dict[str, str] = {}


def load_prompt_text(name: str, role: str) -> str:
    """Load a prompt fragment from ``shared/prompts/{name}.{role}.md``.

    Args:
        name: Logical prompt name (e.g. ``parse_request``, ``nutrition_constraints``).
        role: Message role — ``system`` or ``human``.

    Returns:
        Trimmed prompt text from disk (cached after first load).

    Raises:
        FileNotFoundError: If the ``.md`` file does not exist.
    """
    key = f"{name}.{role}"
    if key not in _cache:
        path = PROMPTS_DIR / f"{name}.{role}.md"
        if not path.is_file():
            raise FileNotFoundError(f"Prompt file not found: {path}")
        _cache[key] = path.read_text(encoding="utf-8").strip()
    return _cache[key]


def chat_prompt(name: str) -> ChatPromptTemplate:
    """Build a two-message ChatPromptTemplate from externalized prompt files.

    Args:
        name: Base name matching ``{name}.system.md`` and ``{name}.human.md``.

    Returns:
        LangChain template with system + human messages. Human template may
        contain ``{variable}`` placeholders for ``.invoke()`` / ``.format()``.
    """
    return ChatPromptTemplate.from_messages([
        ("system", load_prompt_text(name, "system")),
        ("human", load_prompt_text(name, "human")),
    ])
