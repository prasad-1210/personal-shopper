#!/usr/bin/env python3
"""LangGraph agent registry helpers (deploy/agents.manifest.yaml + Helm agent values)."""

from __future__ import annotations

import argparse
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "deploy" / "agents.manifest.yaml"
HELM_AGENTS = ROOT / "deploy" / "helm" / "agents"

# manifest id → deploy/helm/agents/<folder>
HELM_AGENT_DIRS: dict[str, str] = {
    "supervisor": "supervisor",
    "nutrition": "nutrition-agent",
    "recipe": "recipe-agent",
    "shopping": "shopping-agent",
    "budget": "budget-agent",
}


def _load_yaml(path: Path) -> dict:
    if yaml is None:
        raise SystemExit("PyYAML required: pip install pyyaml")
    with path.open() as f:
        data = yaml.safe_load(f)
    return data or {}


def load_manifest() -> list[dict]:
    return list(_load_yaml(MANIFEST).get("agents") or [])


def helm_agent_values(manifest_id: str) -> dict:
    folder = HELM_AGENT_DIRS.get(manifest_id, manifest_id)
    path = HELM_AGENTS / folder / "values.yaml"
    if path.is_file():
        return _load_yaml(path)
    return {}


def buildable_agents() -> list[dict]:
    """Agents with build.config in manifest (LangGraph image build list)."""
    out: list[dict] = []
    for entry in load_manifest():
        agent_id = entry.get("id")
        if not agent_id:
            continue
        build = entry.get("build") or {}
        if not build.get("config"):
            continue
        helm_vals = helm_agent_values(agent_id)
        out.append({**entry, "helm": helm_vals, "id": agent_id, "build": build})
    return out


def image_repository(agent_id: str, prefix: str, explicit: str = "") -> str:
    if explicit:
        return explicit
    return f"{prefix}-{agent_id}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("ids", "build-specs", "image-repos"),
        help="ids | build-specs | image-repos",
    )
    parser.add_argument("--prefix", default="personal-shopper", help="Image repository prefix")
    args = parser.parse_args()

    if args.command == "ids":
        for a in buildable_agents():
            print(a["id"])
        return

    if args.command == "build-specs":
        for a in buildable_agents():
            print(f"{a['id']}:{a['build']['config']}")
        return

    if args.command == "image-repos":
        for a in buildable_agents():
            helm_image = (a.get("helm") or {}).get("image") or {}
            repo = image_repository(
                a["id"],
                args.prefix,
                helm_image.get("repository") or "",
            )
            print(f"{a['id']}:{repo}")
        return


if __name__ == "__main__":
    main()
