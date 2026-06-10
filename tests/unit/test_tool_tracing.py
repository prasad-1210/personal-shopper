"""Tool invoke tracing helpers."""
from unittest.mock import MagicMock

from shared.tool_tracing import invoke_tool


def test_invoke_tool_sets_run_name_and_metadata():
    tool = MagicMock()
    tool.name = "check_product_availability"
    tool.invoke.return_value = {"available": True}

    result = invoke_tool(
        tool,
        {"ingredient": "basil"},
        provider="kroger",
        label="kroger.check_product_availability:basil",
        tags=["shopping_agent"],
        metadata={"ingredient": "basil"},
    )

    assert result == {"available": True}
    tool.invoke.assert_called_once()
    inputs, kwargs = tool.invoke.call_args
    assert inputs[0] == {"ingredient": "basil"}
    config = kwargs["config"]
    assert config["run_name"] == "kroger.check_product_availability:basil"
    assert "tool" in config["tags"]
    assert "kroger" in config["tags"]
    assert "shopping_agent" in config["tags"]
    assert config["metadata"]["tool"] == "check_product_availability"
    assert config["metadata"]["provider"] == "kroger"
    assert config["metadata"]["ingredient"] == "basil"
