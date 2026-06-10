"""
Supervisor — orchestrates sub-agents via RemoteGraph (HTTP).

Entry graph for the Personal Shopper product. Parses user messages, finds a
store, and routes deterministically to nutrition, recipe, shopping, and budget
sub-agents until a markdown shopping list is produced.

Local dev: supervisor :22000, sub-agents :22001–:22004.
Integration spec: docs/agents/supervisor.md
"""
import os
import re

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph._internal._config import merge_configs
from langgraph.config import get_config
from langgraph.graph import END, START, StateGraph
from langgraph.pregel.remote import RemoteGraph

from shared.prompt_loader import chat_prompt
from shared.state import AgentState, ShoppingRequest

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

NUTRITION_AGENT_URL = os.environ.get("NUTRITION_AGENT_URL", "http://127.0.0.1:22001")
RECIPE_AGENT_URL = os.environ.get("RECIPE_AGENT_URL", "http://127.0.0.1:22002")
SHOPPING_AGENT_URL = os.environ.get("SHOPPING_AGENT_URL", "http://127.0.0.1:22003")
BUDGET_AGENT_URL = os.environ.get("BUDGET_AGENT_URL", "http://127.0.0.1:22004")

KROGER_FAMILY = {
    "kroger", "ralphs", "king soopers", "fred meyer",
    "fry's", "harris teeter", "smith's", "foodsco",
}
RAPIDAPI_RETAILERS = {
    "walmart", "target", "costco", "amazon", "bestbuy", "best buy",
}


_REMOTE_GRAPHS: dict[str, RemoteGraph] = {}


def _remote(name: str, url: str) -> RemoteGraph:
    """RemoteGraph client with LangSmith distributed tracing (langsmith-trace headers)."""
    if name not in _REMOTE_GRAPHS:
        _REMOTE_GRAPHS[name] = RemoteGraph(
            name,
            url=url,
            distributed_tracing=True,
        )
    return _REMOTE_GRAPHS[name]


def _remote_invoke_config(agent_name: str) -> RunnableConfig:
    """Build RunnableConfig with LangSmith correlation metadata for RemoteGraph.

    Propagates parent ``thread_id`` and ``run_id`` into sub-agent trace metadata.
    Checkpoint ``thread_id`` remains on the supervisor process only.
    """
    try:
        parent = get_config()
    except RuntimeError:
        return {"metadata": {"remote_agent": agent_name}}

    parent_configurable = parent.get("configurable") or {}
    metadata = dict(parent.get("metadata") or {})
    metadata["remote_agent"] = agent_name
    if thread_id := parent_configurable.get("thread_id"):
        metadata["parent_thread_id"] = thread_id
    if run_id := parent.get("run_id"):
        metadata["parent_run_id"] = str(run_id)

    config: RunnableConfig = {"metadata": metadata}
    if tags := parent.get("tags"):
        config["tags"] = list(tags)
    return config


def _invoke_remote(
    agent_name: str,
    url: str,
    state: AgentState,
    *,
    extra_tags: list[str] | None = None,
    extra_metadata: dict | None = None,
) -> dict:
    """Invoke a sub-agent graph over HTTP and return its output state dict."""
    config = _remote_invoke_config(agent_name)
    if extra_tags or extra_metadata:
        patch: RunnableConfig = {}
        if extra_tags:
            patch["tags"] = [*config.get("tags", []), *extra_tags]
        if extra_metadata:
            patch["metadata"] = {**(config.get("metadata") or {}), **extra_metadata}
        config = merge_configs(config, patch)
    return _remote(agent_name, url).invoke(state, config=config)


def _get_retailer(state: AgentState) -> str:
    """Return normalised retailer key from ``request.preferred_retailer``."""
    req = state.get("request") or {}
    retailer = req.get("preferred_retailer", "kroger") if isinstance(req, dict) \
        else getattr(req, "preferred_retailer", "kroger")
    retailer = str(retailer).lower().strip()
    if retailer in KROGER_FAMILY:
        return "kroger"
    if retailer in RAPIDAPI_RETAILERS:
        return retailer
    return "kroger"


def _uses_rapidapi(retailer: str) -> bool:
    """Return True if retailer uses RapidAPI catalog (not Kroger inventory)."""
    return retailer in RAPIDAPI_RETAILERS


def receive_message(state: AgentState) -> dict:
    """Reset per-run workflow fields at the start of each user message.

    Clears recipes, ingredients, agent_steps, counters, and errors so a
    checkpointed thread does not leak state from a prior run.
    """
    return {
        "iteration": 0,
        "budget_status": "unchecked",
        "nutrition_status": "unchecked",
        "constraint_violations": [],
        "selected_recipes": [],
        "ingredients": [],
        "shopping_list": [],
        "agent_steps": [],
        "next_agent": "",
        "error": None,
        "nutrition_constraints": None,
        "location_id": None,
        "store_name": None,
        "request": None,
    }


_UI_PREFIX_RE = re.compile(r"^\[([^\]]+)\]\s*\n?", re.MULTILINE)


def _parse_ui_constraints(content: str) -> dict[str, str]:
    """Parse [Zip: 75035 | Retailer: kroger | ...] prefix from UI messages."""
    match = _UI_PREFIX_RE.match(content.strip())
    if not match:
        return {}
    out: dict[str, str] = {}
    for part in match.group(1).split("|"):
        part = part.strip()
        if ":" not in part:
            continue
        key, val = part.split(":", 1)
        out[key.strip().lower()] = val.strip()
    return out


def _set_request_field(result: ShoppingRequest | dict, name: str, value) -> None:
    if isinstance(result, dict):
        result[name] = value
    else:
        setattr(result, name, value)


def _split_ui_prefix_and_body(content: str) -> tuple[dict[str, str], str]:
    """Return (sidebar defaults from prefix, user message body)."""
    text = content.strip()
    match = _UI_PREFIX_RE.match(text)
    if not match:
        return {}, text
    return _parse_ui_constraints(text), text[match.end() :].strip()


def _get_request_field(result: ShoppingRequest | dict, name: str):
    if isinstance(result, dict):
        return result.get(name)
    return getattr(result, name, None)


def _body_mentions_zip(body: str) -> bool:
    return bool(re.search(r"\b\d{5}\b", body))


def _body_mentions_retailer(body: str) -> bool:
    lower = body.lower()
    names = (
        "walmart", "target", "costco", "amazon", "best buy", "bestbuy",
        "kroger", "ralphs", "fred meyer", "king soopers", "harris teeter",
    )
    return any(name in lower for name in names)


def _body_mentions_diet(body: str) -> bool:
    lower = body.lower()
    terms = (
        "diabetic", "vegan", "vegetarian", "low-carb", "low carb",
        "keto", "gluten-free", "gluten free", "dairy-free", "dairy free",
    )
    return any(term in lower for term in terms)


def _body_mentions_budget(body: str) -> bool:
    return bool(re.search(r"\$|budget|under\s+\d", body, re.IGNORECASE))


def _body_mentions_calories(body: str) -> bool:
    return bool(re.search(r"\bcal(orie)?s?\b", body, re.IGNORECASE))


def _body_mentions_servings(body: str) -> bool:
    return bool(
        re.search(
            r"\bfor\s+\d+\b|\bservings?\b|\bfeeds?\s+\d+\b|\b\d+\s+people\b",
            body,
            re.IGNORECASE,
        )
    )


def _apply_ui_defaults(
    result: ShoppingRequest | dict,
    constraints: dict[str, str],
    body: str,
) -> None:
    """Fill from sidebar only when the user message did not specify that field."""
    if not constraints:
        return

    if not _body_mentions_zip(body):
        zip_val = constraints.get("zip")
        if zip_val:
            digits = re.sub(r"\D", "", zip_val)[:5]
            if len(digits) == 5:
                _set_request_field(result, "zip_code", digits)

    if not _body_mentions_retailer(body):
        retailer = constraints.get("retailer")
        if retailer:
            _set_request_field(result, "preferred_retailer", retailer.lower())

    if not _body_mentions_diet(body):
        diet = constraints.get("diet")
        if diet:
            _set_request_field(result, "dietary_profile", diet.lower())

    if not _body_mentions_budget(body) and _get_request_field(result, "budget_usd") is None:
        budget = constraints.get("budget")
        if budget:
            match = re.search(r"[\d.]+", budget.replace(",", ""))
            if match:
                _set_request_field(result, "budget_usd", float(match.group()))

    if not _body_mentions_calories(body) and _get_request_field(
        result, "max_calories_per_serving"
    ) is None:
        calories = constraints.get("max calories")
        if calories:
            match = re.search(r"[\d.]+", calories)
            if match:
                _set_request_field(result, "max_calories_per_serving", float(match.group()))

    if not _body_mentions_servings(body):
        servings = constraints.get("servings")
        if servings:
            match = re.search(r"\d+", servings)
            if match:
                _set_request_field(result, "servings", int(match.group()))


def parse_request(state: AgentState) -> dict:
    """Extract ``ShoppingRequest`` from the latest human message via LLM.

    Merges UI sidebar defaults (zip, retailer, diet, budget) when the user
    message body does not mention those fields. Prompt: ``shared/prompts/parse_request``.
    """
    messages = state.get("messages", [])
    last_content = None
    for m in reversed(messages):
        if hasattr(m, "type") and m.type == "human":
            last_content = m.content
            break
        if isinstance(m, dict) and m.get("role") in ("user", "human"):
            last_content = m.get("content", "")
            break
        if isinstance(m, HumanMessage):
            last_content = m.content
            break

    if not last_content:
        return {"error": "No user message found"}

    ui_defaults, body = _split_ui_prefix_and_body(last_content)
    parse_text = body or last_content

    structured_llm = llm.with_structured_output(ShoppingRequest)
    result = (chat_prompt("parse_request") | structured_llm).invoke({"message": parse_text})
    if isinstance(result, dict):
        result["raw_message"] = last_content
    else:
        result.raw_message = last_content
    _apply_ui_defaults(result, ui_defaults, parse_text)

    # Fresh workflow for each new user message (thread checkpoint may carry old state)
    return {
        "request": result,
        "agent_steps": ["parse_request"],
        "iteration": 0,
        "refinement_count": 0,
        "next_agent": "",
        "budget_status": "unchecked",
        "nutrition_status": "unchecked",
        "nutrition_constraints": {},
        "constraint_violations": [],
        "selected_recipes": [],
        "ingredients": [],
        "shopping_list": [],
        "error": None,
    }


def find_store(state: AgentState) -> dict:
    """Resolve store ``location_id`` and ``store_name`` for the user's zip.

    Uses Kroger ``find_nearest_store`` for Kroger-family retailers, or RapidAPI
    placeholder for Walmart/Target/Costco/Amazon. Respects ``USE_MOCK_TOOLS``.
    """
    zip_code = "94103"
    req = state.get("request")
    if req:
        zip_code = req.get("zip_code", "94103") if isinstance(req, dict) \
            else getattr(req, "zip_code", "94103")

    retailer = _get_retailer(state)
    use_mock = os.environ.get("USE_MOCK_TOOLS", "false").lower() == "true"

    from shared.tool_tracing import invoke_tool

    if retailer == "kroger":
        if use_mock:
            from personal_shopper.tools.mock_tools import find_nearest_store
            provider = "mock"
        else:
            from personal_shopper.tools.kroger import find_nearest_store
            provider = "kroger"
        result = invoke_tool(
            find_nearest_store,
            {"zip_code": zip_code},
            provider=provider,
            label=f"{provider}.find_nearest_store:{zip_code}",
            tags=["find_store", "kroger"],
            metadata={"zip_code": zip_code, "retailer": "kroger"},
        )
    else:
        if use_mock:
            from personal_shopper.tools.mock_tools import (
                find_nearest_store as find_store_fn,
            )
            provider = "mock"
        else:
            from personal_shopper.tools.rapidapi_search import (
                find_nearest_store as find_store_fn,
            )
            provider = "rapidapi"
        result = invoke_tool(
            find_store_fn,
            {"zip_code": zip_code},
            provider=provider,
            label=f"{provider}.find_nearest_store:{zip_code}@{retailer}",
            tags=["find_store", retailer],
            metadata={"zip_code": zip_code, "retailer": retailer},
        )

    steps = list(state.get("agent_steps", []))
    steps.append("find_store")
    return {
        "location_id": result.get("location_id"),
        "store_name": result.get("name", retailer.title()),
        "agent_steps": steps,
    }


MAX_SUPERVISOR_TURNS = 12   # safety cap per user message
MAX_BUDGET_RETRIES = 3


def _req_field(state: AgentState, field: str, default=None):
    req = state.get("request") or {}
    return req.get(field, default) if isinstance(req, dict) \
        else getattr(req, field, default)


def _decide_next_agent(state: AgentState) -> str:
    """Return the next graph node name using ordered deterministic rules.

    Order: nutrition → recipe → shopping → budget → recipe retry → finish.
    See docs/agents/supervisor.md for the full routing table.
    """
    profile = _req_field(state, "dietary_profile", "")
    max_cal = _req_field(state, "max_calories_per_serving")
    budget = _req_field(state, "budget_usd")

    if (profile or max_cal) and state.get("nutrition_status", "unchecked") == "unchecked":
        return "nutrition_agent"

    if not state.get("selected_recipes"):
        return "recipe_agent"

    if not state.get("shopping_list"):
        return "shopping_agent"

    if budget and state.get("budget_status", "unchecked") == "unchecked":
        return "budget_agent"

    if state.get("budget_status") == "over":
        if state.get("refinement_count", 0) < MAX_BUDGET_RETRIES:
            return "recipe_agent"

    if state.get("nutrition_status") == "fail":
        if state.get("refinement_count", 0) < MAX_BUDGET_RETRIES:
            return "recipe_agent"

    return "finish_node"


def _summarise(state: AgentState) -> str:
    ings = state.get("ingredients", [])
    total = sum(
        (i.get("price") or 0) if isinstance(i, dict) else (i.price or 0)
        for i in ings
    )
    return (
        f"dietary_profile={_req_field(state, 'dietary_profile') or 'none'} | "
        f"max_calories={_req_field(state, 'max_calories_per_serving') or 'none'} | "
        f"budget={_req_field(state, 'budget_usd') or 'none'} | "
        f"recipes={len(state.get('selected_recipes', []))} | "
        f"ingredients={len(ings)} | "
        f"shopping_list={len(state.get('shopping_list', [])) > 0} | "
        f"estimated_total=${total:.2f} | "
        f"budget_status={state.get('budget_status', 'unchecked')} | "
        f"nutrition_status={state.get('nutrition_status', 'unchecked')} | "
        f"violations={state.get('constraint_violations', [])} | "
        f"supervisor_turn={state.get('iteration', 0)}"
    )


def supervisor_node(state: AgentState) -> dict:
    """Increment turn counter and set ``next_agent`` for the conditional router."""
    turns = state.get("iteration", 0)
    if turns >= MAX_SUPERVISOR_TURNS:
        decision = "finish_node"
    else:
        decision = _decide_next_agent(state)

    steps = list(state.get("agent_steps", []))
    steps.append(f"supervisor→{decision}")
    return {
        "next_agent": decision,
        "iteration": turns + 1,
        "agent_steps": steps,
    }


def supervisor_router(state: AgentState) -> str:
    """Conditional edge function: route to ``next_agent`` node name."""
    return state.get("next_agent", "finish_node")


def _merge_remote_result(state: AgentState, result: dict, step_name: str) -> dict:
    """Merge RemoteGraph output into supervisor state."""
    if not isinstance(result, dict):
        return {"error": f"{step_name}: invalid remote response", "agent_steps": state.get("agent_steps", [])}

    steps = list(state.get("agent_steps", []))
    remote_steps = result.get("agent_steps")
    if isinstance(remote_steps, list) and remote_steps:
        steps = remote_steps
    elif step_name not in str(steps):
        steps.append(step_name)

    merged = {"agent_steps": steps}
    for key, value in result.items():
        if key != "agent_steps" and value is not None:
            merged[key] = value
    return merged


def call_nutrition_agent(state: AgentState) -> dict:
    """RemoteGraph invoke: nutrition agent. Merges result into supervisor state."""
    try:
        result = _invoke_remote(
            "nutrition_agent",
            NUTRITION_AGENT_URL,
            state,
            extra_tags=["nutrition_agent", "supervisor_call"],
            extra_metadata={
                "supervisor_iteration": state.get("iteration", 0),
                "called_by": "supervisor",
                "agent": "nutrition_agent",
            },
        )
        return _merge_remote_result(state, result, "nutrition_agent")
    except Exception as e:
        steps = list(state.get("agent_steps", []))
        steps.append("nutrition_agent:error")
        return {"error": str(e), "nutrition_status": "ok", "agent_steps": steps}


def call_recipe_agent(state: AgentState) -> dict:
    """RemoteGraph invoke: recipe agent. Increments ``refinement_count`` on budget retry."""
    try:
        result = _invoke_remote(
            "recipe_agent",
            RECIPE_AGENT_URL,
            state,
            extra_tags=["recipe_agent", "supervisor_call"],
            extra_metadata={
                "supervisor_iteration": state.get("iteration", 0),
                "called_by": "supervisor",
                "agent": "recipe_agent",
                "budget_status": state.get("budget_status", "unchecked"),
            },
        )
        merged = _merge_remote_result(state, result, "recipe_agent")
        if state.get("budget_status") == "over":
            merged["refinement_count"] = state.get("refinement_count", 0) + 1
        merged.setdefault("budget_status", "unchecked")
        return merged
    except Exception as e:
        steps = list(state.get("agent_steps", []))
        steps.append("recipe_agent:error")
        return {"error": str(e), "agent_steps": steps}


def call_shopping_agent(state: AgentState) -> dict:
    """RemoteGraph invoke: shopping agent. Passes retailer in trace metadata."""
    try:
        result = _invoke_remote(
            "shopping_agent",
            SHOPPING_AGENT_URL,
            state,
            extra_tags=["shopping_agent", "supervisor_call"],
            extra_metadata={
                "supervisor_iteration": state.get("iteration", 0),
                "called_by": "supervisor",
                "agent": "shopping_agent",
                "retailer": _get_retailer(state),
            },
        )
        return _merge_remote_result(state, result, "shopping_agent")
    except Exception as e:
        steps = list(state.get("agent_steps", []))
        steps.append("shopping_agent:error")
        return {"error": str(e), "agent_steps": steps}


def call_budget_agent(state: AgentState) -> dict:
    """RemoteGraph invoke: budget agent. Includes estimated total in metadata."""
    try:
        ingredients = state.get("ingredients", [])
        total = sum(
            (i.get("price") or 0) if isinstance(i, dict) else (i.price or 0)
            for i in ingredients
        )
        result = _invoke_remote(
            "budget_agent",
            BUDGET_AGENT_URL,
            state,
            extra_tags=["budget_agent", "supervisor_call"],
            extra_metadata={
                "supervisor_iteration": state.get("iteration", 0),
                "called_by": "supervisor",
                "agent": "budget_agent",
                "estimated_total": round(total, 2),
                "budget_limit": _req_field(state, "budget_usd"),
            },
        )
        return _merge_remote_result(state, result, "budget_agent")
    except Exception as e:
        steps = list(state.get("agent_steps", []))
        steps.append("budget_agent:error")
        return {"error": str(e), "agent_steps": steps}


def finish_node(state: AgentState) -> dict:
    """Format ingredients into a markdown shopping list ``AIMessage``.

    Groups by aisle, shows prices/availability, budget and diet status icons.
    Returns a helpful error message when recipes or ingredients are missing.
    """
    ingredients = state.get("ingredients", [])
    recipes = state.get("selected_recipes", [])
    store = state.get("store_name", "your store")
    retailer = _get_retailer(state)

    if not ingredients:
        steps = list(state.get("agent_steps", []))
        steps.append("finish_node")
        err = state.get("error")
        hint = f"\n\n(Technical detail: {err})" if err else ""
        recipes = state.get("selected_recipes", [])
        if not recipes:
            msg = (
                "I couldn't find recipes for your request. "
                "Try a simpler dish name or check that the recipe agent is running "
                f"(RECIPE_AGENT_URL={RECIPE_AGENT_URL})."
            )
        else:
            msg = (
                "I found recipes but couldn't build a shopping list. "
                "Check that the shopping agent is running "
                f"(SHOPPING_AGENT_URL={SHOPPING_AGENT_URL})."
            )
        return {
            "shopping_list": [],
            "messages": [AIMessage(content=msg + hint)],
            "agent_steps": steps,
        }

    by_aisle: dict[str, list] = {}
    for ing in ingredients:
        aisle = (ing.get("aisle") if isinstance(ing, dict) else ing.aisle) or "Other"
        by_aisle.setdefault(aisle, []).append(ing)

    lines = [f"## 🛒 Shopping List — {store}\n"]
    titles = ", ".join(r.get("title", "") for r in recipes)
    lines.append(f"**Recipes:** {titles}\n")

    if _uses_rapidapi(retailer):
        lines.append(
            f"> ⚠️ {retailer.title()} catalog via Google Shopping — "
            "prices approximate, in-store availability not confirmed.\n"
        )

    total = 0.0
    for aisle in sorted(by_aisle.keys()):
        lines.append(f"\n### {aisle}")
        for ing in by_aisle[aisle]:
            if isinstance(ing, dict):
                orig = ing.get("original", "")
                avail = ing.get("available", False)
                desc = ing.get("product_description", "")
                price = ing.get("price")
                sub = ing.get("substitute", "")
            else:
                orig = ing.original
                avail = ing.available
                desc = ing.product_description or ""
                price = ing.price
                sub = ing.substitute or ""

            if avail:
                p = f" — ${price:.2f}" if price else ""
                d = f" ({desc})" if desc else ""
                lines.append(f"- ✓ {orig}{d}{p}")
                if price:
                    total += price
            else:
                s = f" 💡 sub: *{sub}*" if sub else ""
                lines.append(f"- ✗ {orig} *(not available)*{s}")

    lines.append("\n---")
    req = state.get("request") or {}

    def get(field: str, default=None):
        return req.get(field, default) if isinstance(req, dict) \
            else getattr(req, field, default)

    budget = get("budget_usd")
    profile = get("dietary_profile", "")
    violations = state.get("constraint_violations", [])

    if total > 0:
        lines.append(f"\n**Estimated total:** ${total:.2f}")
        if budget:
            icon = "✅" if state.get("budget_status") == "ok" else "⚠️"
            lines.append(f"{icon} Budget: ${budget:.2f} limit")

    if profile:
        icon = "✅" if state.get("nutrition_status") == "ok" else "⚠️"
        lines.append(f"{icon} {profile.title()} profile applied")

    for v in violations:
        lines.append(f"⚠️ {v}")

    # Count actual recipe re-runs from agent_steps (not supervisor calls)
    recipe_runs = sum(1 for s in state.get("agent_steps", []) if "recipe_agent" in s)
    if recipe_runs > 1:
        lines.append(f"ℹ️ Refined over {recipe_runs} recipe searches")

    steps = list(state.get("agent_steps", []))
    steps.append("finish_node")
    return {
        "shopping_list": ingredients,
        "messages": [AIMessage(content="\n".join(lines))],
        "agent_steps": steps,
    }


def build_graph():
    """Wire supervisor StateGraph: parse → store → supervisor loop → finish."""
    builder = StateGraph(AgentState)

    builder.add_node("receive_message", receive_message)
    builder.add_node("parse_request", parse_request)
    builder.add_node("find_store", find_store)
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("nutrition_agent", call_nutrition_agent)
    builder.add_node("recipe_agent", call_recipe_agent)
    builder.add_node("shopping_agent", call_shopping_agent)
    builder.add_node("budget_agent", call_budget_agent)
    builder.add_node("finish_node", finish_node)

    builder.add_edge(START, "receive_message")
    builder.add_edge("receive_message", "parse_request")
    builder.add_edge("parse_request", "find_store")
    builder.add_edge("find_store", "supervisor")

    builder.add_conditional_edges(
        "supervisor",
        supervisor_router,
        {
            "nutrition_agent": "nutrition_agent",
            "recipe_agent": "recipe_agent",
            "shopping_agent": "shopping_agent",
            "budget_agent": "budget_agent",
            "finish_node": "finish_node",
        },
    )

    builder.add_edge("nutrition_agent", "supervisor")
    builder.add_edge("recipe_agent", "supervisor")
    builder.add_edge("shopping_agent", "supervisor")
    builder.add_edge("budget_agent", "supervisor")
    builder.add_edge("finish_node", END)

    return builder.compile()


graph = build_graph()
