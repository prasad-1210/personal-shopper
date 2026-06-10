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
  """Wrap a compiled graph for ``langgraph.json`` with LangSmith trace nesting.

  Sub-agents export ``graph`` as this context-manager factory so ``RemoteGraph``
  (with ``distributed_tracing=True``) can attach child runs under the supervisor.

  Args:
      compiled_graph: ``builder.compile()`` result from a sub-agent StateGraph.
      agent_tag: Default LangSmith tag (e.g. ``nutrition_agent``).

  Returns:
      Callable ``graph(config)`` suitable for ``langgraph.json`` ``graphs`` export.
      Reads ``langsmith-trace``, ``langsmith-project``, metadata, and tags from
      ``config["configurable"]`` set by the supervisor's RemoteGraph client.
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
