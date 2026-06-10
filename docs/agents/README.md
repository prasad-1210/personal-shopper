# Agent integration specifications

Swagger-style documentation for Personal Shopper LangGraph agents. For external teams integrating via HTTP without reading the Python codebase.

## Start here

1. **[API-CONTRACT.md](API-CONTRACT.md)** — shared HTTP API, `AgentState` schema, auth, tracing
2. **Per-agent specs** — graph behavior, required inputs, outputs, examples

## Agents

Each spec includes a **Tools & external APIs** section (inputs, outputs, provider routing, trace names, env vars).

| Agent | Role | Tools | Spec |
|-------|------|-------|------|
| **Supervisor** | Parse, store lookup, orchestration | `find_nearest_store` | [supervisor.md](supervisor.md) |
| **Nutrition** | Diet → JSON constraints | LLM only | [nutrition-agent.md](nutrition-agent.md) |
| **Recipe** | Recipe search | `search_recipes` | [recipe-agent.md](recipe-agent.md) |
| **Shopping** | Stock + substitutes | `get_recipe_ingredients`, `check_product_availability`, `get_ingredient_substitutes` | [shopping-agent.md](shopping-agent.md) |
| **Budget** | Sum vs budget | None (uses upstream prices) | [budget-agent.md](budget-agent.md) |

Master tool catalog: [TOOLS.md](../TOOLS.md)

## Integration patterns

| Pattern | When to use |
|---------|-------------|
| **Call supervisor only** | Full shopping-list flow (recommended) |
| **Call sub-agent directly** | Embed one capability (e.g. recipe search only) |
| **RemoteGraph from another LangGraph** | Same as supervisor pattern; set `distributed_tracing=True` |

## Related docs

- [ARCHITECTURE.md](../ARCHITECTURE.md) — design decisions, deployment
- [TOOLS.md](../TOOLS.md) — external API tool catalog
