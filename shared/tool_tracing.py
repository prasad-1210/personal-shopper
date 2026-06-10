"""Named LangSmith runs for imperative ``tool.invoke()`` calls inside graph nodes."""
from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool


def invoke_tool(
  tool: BaseTool,
  inputs: dict[str, Any],
  *,
  label: str | None = None,
  provider: str | None = None,
  tags: list[str] | None = None,
  metadata: dict[str, Any] | None = None,
) -> Any:
  """Invoke a LangChain tool with a readable LangSmith run name and metadata.

  Use inside graph nodes (not LLM ``tool_calls``) so traces show names like
  ``kroger.check_product_availability:basil`` instead of repeated generic names.

  Args:
      tool: LangChain ``@tool`` runnable to invoke.
      inputs: Tool input dict (same as ``tool.invoke(inputs)``).
      label: LangSmith ``run_name``; defaults to ``{provider}.{tool.name}``.
      provider: Provider tag for traces (``kroger``, ``edamam``, ``mock``, …).
      tags: Extra LangSmith tags appended after ``tool`` and ``provider``.
      metadata: Extra metadata merged with ``tool`` and ``provider`` keys.

  Returns:
      Tool return value (provider-specific dict or list).
  """
  tool_name = getattr(tool, "name", type(tool).__name__)
  run_name = label or (f"{provider}.{tool_name}" if provider else tool_name)

  tag_list = ["tool"]
  if provider:
    tag_list.append(provider)
  if tags:
    tag_list.extend(tags)

  meta: dict[str, Any] = {"tool": tool_name}
  if provider:
    meta["provider"] = provider
  if metadata:
    meta.update(metadata)

  config = RunnableConfig(run_name=run_name, tags=tag_list, metadata=meta)
  return tool.invoke(inputs, config=config)
