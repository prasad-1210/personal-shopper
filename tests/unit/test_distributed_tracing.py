"""Distributed tracing graph export."""
import os

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("LANGSMITH_TRACING", "false")
os.environ.setdefault("USE_MOCK_TOOLS", "true")


def test_sub_agents_export_contextmanager_graph():
    from agents.budget_agent.graph import graph as bg
    from agents.nutrition_agent.graph import graph as ng
    from agents.recipe_agent.graph import graph as rg
    from agents.shopping_agent.graph import graph as sg

    for name, g in [
        ("nutrition", ng),
        ("recipe", rg),
        ("shopping", sg),
        ("budget", bg),
    ]:
        assert callable(g), f"{name} graph should be callable"
        cm = g({})
        assert hasattr(cm, "__enter__") and hasattr(cm, "__exit__")


def test_export_traced_graph_yields_compiled():
    from shared.distributed_tracing import export_traced_graph

    sentinel = object()
    traced = export_traced_graph(sentinel, "test_agent")
    with traced({}) as compiled:
        assert compiled is sentinel
