"""Supervisor RemoteGraph tracing helpers."""
import os
from unittest.mock import patch
from uuid import uuid4

os.environ.setdefault("OPENAI_API_KEY", "test-key")

from supervisor.graph import _remote_invoke_config


def test_remote_invoke_config_without_runnable_context():
    config = _remote_invoke_config("recipe_agent")
    assert config == {"metadata": {"remote_agent": "recipe_agent"}}


def test_split_ui_prefix_and_body():
    from supervisor.graph import _split_ui_prefix_and_body

    defaults, body = _split_ui_prefix_and_body(
        "[Zip: 75035 | Servings: 4]\n\nPalak paneer for 4"
    )
    assert defaults.get("zip") == "75035"
    assert body == "Palak paneer for 4"


def test_remote_invoke_config_inherits_parent_metadata():
    run_id = uuid4()
    parent = {
        "run_id": run_id,
        "configurable": {"thread_id": "chat-thread-abc"},
        "metadata": {"langgraph_node": "supervisor"},
        "tags": ["personal-shopper"],
    }
    with patch("supervisor.graph.get_config", return_value=parent):
        config = _remote_invoke_config("shopping_agent")

    assert config["tags"] == ["personal-shopper"]
    assert config["metadata"]["remote_agent"] == "shopping_agent"
    assert config["metadata"]["parent_thread_id"] == "chat-thread-abc"
    assert config["metadata"]["parent_run_id"] == str(run_id)
    assert config["metadata"]["langgraph_node"] == "supervisor"
    assert "thread_id" not in config.get("configurable", {})
