"""Externalized prompt templates."""
from shared.prompt_loader import chat_prompt, load_prompt_text


def test_load_parse_request_prompts():
    system = load_prompt_text("parse_request", "system")
    human = load_prompt_text("parse_request", "human")
    assert "meal_keywords" in system
    assert "{message}" in human


def test_load_nutrition_constraints_prompts():
    system = load_prompt_text("nutrition_constraints", "system")
    human = load_prompt_text("nutrition_constraints", "human")
    assert "diabetic" in system
    assert "{profile}" in human
    assert "{calories}" in human


def test_chat_prompt_builds_template():
    prompt = chat_prompt("parse_request")
    messages = prompt.format_messages(message="pasta near 94103")
    assert messages[0].type == "system"
    assert "meal_keywords" in messages[0].content
    assert messages[1].content == "pasta near 94103"
