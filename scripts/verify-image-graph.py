#!/usr/bin/env python3
"""Verify a LangGraph wolfi image can load its registered graph(s).

Wolfi images expose graphs via LANGSERVE_GRAPHS (file paths under /deps/...),
not as importable top-level packages like supervisor.graph.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys


def load_graph(path_attr: str):
    path, attr = path_attr.rsplit(":", 1)
    spec = importlib.util.spec_from_file_location("_lg_graph_module", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load graph module from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    graph = getattr(mod, attr)
    if graph is None:
        raise ValueError(f"graph attribute {attr!r} is None in {path}")
    return graph


def main() -> int:
    raw = os.environ.get("LANGSERVE_GRAPHS")
    if not raw:
        print("LANGSERVE_GRAPHS not set in image", file=sys.stderr)
        return 1

    specs = json.loads(raw)
    if not specs:
        print("LANGSERVE_GRAPHS is empty", file=sys.stderr)
        return 1

    for graph_id, path_attr in specs.items():
        load_graph(path_attr)
        print(f"{graph_id} graph load OK ({path_attr})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
