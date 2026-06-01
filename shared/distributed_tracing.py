"""Server-side LangSmith distributed tracing for sub-agent LangGraph exports."""
from __future__ import annotations

import contextlib
import os
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from typing import Any

import langsmith as ls

GraphFactory = Callable[[dict[str, Any] | None], AbstractContextManager[Any]]


def export_traced_graph(compiled_graph: Any, agent_tag: str) -> GraphFactory:
    """
    Export a compiled graph as a @contextmanager for langgraph.json.

    Reads langsmith-trace / project / metadata / tags from config.configurable
    (set by RemoteGraph with distributed_tracing=True on the supervisor).
    """

    @contextlib.contextmanager
    def graph(config: dict[str, Any] | None) -> Iterator[Any]:
        configurable = (config or {}).get("configurable", {})
        parent_trace = configurable.get("langsmith-trace")
        parent_project = configurable.get("langsmith-project")
        metadata = configurable.get("langsmith-metadata")
        tags = configurable.get("langsmith-tags")

        tag_list = list(tags) if tags else [agent_tag]

        with ls.tracing_context(
            parent=parent_trace,
            project_name=parent_project or os.environ.get("LANGSMITH_PROJECT"),
            metadata=metadata,
            tags=tag_list,
        ):
            yield compiled_graph

    return graph
