# Prompt templates

Editable LLM prompts for agents. Loaded at runtime by `shared/prompt_loader.py`.

| File pair | Used by | Variables |
|-----------|---------|-----------|
| `parse_request.*` | `supervisor/graph.py` → `parse_request` | `{message}` |
| `nutrition_constraints.*` | `agents/nutrition_agent/graph.py` | `{profile}`, `{calories}` |

**Naming:** `<prompt_name>.system.md` and `<prompt_name>.human.md`

**LangChain escaping:** Use `{{` and `}}` in `.md` files when the model must see literal braces (e.g. JSON schema).

After editing prompts, update [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) if behavior or variables change.
