"""
DEPRECATED: Monolithic supervisor graph (pre–Phase 3).
The active entry point is supervisor/graph.py (multi-agent via RemoteGraph).
Kept for reference only — not registered in langgraph.json.

Personal Shopper — Supervisor Agent Graph

Architecture:
  START → receive_message → parse_request → find_store → supervisor
  supervisor (conditional) →
    nutrition_agent → supervisor
    recipe_agent    → supervisor
    shopping_agent  → supervisor
    budget_agent    → supervisor
    finish_node     → END
"""
import json
import os

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from personal_shopper.state import AgentState, IngredientAvailability, ShoppingRequest

# ── Tool selection ─────────────────────────────────────────────────────────────
USE_MOCK = os.environ.get("USE_MOCK_TOOLS", "false").lower() == "true"
RECIPE_PROVIDER = os.environ.get("RECIPE_PROVIDER", "edamam")

if USE_MOCK:
    from personal_shopper.tools.mock_tools import (
        check_product_availability as kroger_check_availability,
    )
    from personal_shopper.tools.mock_tools import (
        check_product_availability as rapidapi_check_availability,
    )
    from personal_shopper.tools.mock_tools import (
        find_nearest_store as kroger_find_store,
    )
    from personal_shopper.tools.mock_tools import (
        find_nearest_store as rapidapi_find_store,
    )
    from personal_shopper.tools.mock_tools import (
        get_ingredient_substitutes,
        get_recipe_ingredients,
        search_recipes,
    )
else:
    from personal_shopper.tools.kroger import (
        check_product_availability as kroger_check_availability,
    )
    from personal_shopper.tools.kroger import (
        find_nearest_store as kroger_find_store,
    )
    from personal_shopper.tools.rapidapi_search import (
        check_product_availability as rapidapi_check_availability,
    )
    from personal_shopper.tools.rapidapi_search import (
        find_nearest_store as rapidapi_find_store,
    )
    if RECIPE_PROVIDER == "edamam":
        from personal_shopper.tools.edamam import (
            get_ingredient_substitutes,
            get_recipe_ingredients,
            search_recipes,
        )
    else:
        from personal_shopper.tools.spoonacular import (
            get_ingredient_substitutes,
            get_recipe_ingredients,
            search_recipes,
        )

# ── LLM ───────────────────────────────────────────────────────────────────────
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# ── Retailer routing ──────────────────────────────────────────────────────────
KROGER_FAMILY = {
    "kroger", "ralphs", "king soopers", "fred meyer",
    "fry's", "harris teeter", "smith's", "foodsco",
}
RAPIDAPI_RETAILERS = {
    "walmart", "target", "costco", "amazon", "bestbuy", "best buy",
}


def _get_retailer(state: AgentState) -> str:
    req = state.get("request")
    if not req:
        return "kroger"
    retailer = (
        req.get("preferred_retailer", "kroger") if isinstance(req, dict)
        else getattr(req, "preferred_retailer", "kroger")
    )
    retailer = str(retailer).lower().strip()
    if retailer in KROGER_FAMILY:
        return "kroger"
    if retailer in RAPIDAPI_RETAILERS:
        return retailer
    return "kroger"


def _uses_rapidapi(retailer: str) -> bool:
    return retailer in RAPIDAPI_RETAILERS


# ── Helper: extract request field ────────────────────────────────────────────
def _req(state: AgentState, field: str, default=None):
    req = state.get("request")
    if not req:
        return default
    return req.get(field, default) if isinstance(req, dict) \
        else getattr(req, field, default)


# ── Node: receive_message ─────────────────────────────────────────────────────
def receive_message(state: AgentState) -> dict:
    return {}


# ── Node: parse_request ───────────────────────────────────────────────────────
def parse_request(state: AgentState) -> dict:
    messages = state.get("messages", [])
    last_content = None
    for m in reversed(messages):
        if hasattr(m, "type") and m.type == "human":
            last_content = m.content
            break
        elif isinstance(m, dict) and m.get("role") in ("user", "human"):
            last_content = m.get("content", "")
            break
        elif isinstance(m, HumanMessage):
            last_content = m.content
            break

    if not last_content:
        return {"error": "No user message found"}

    structured_llm = llm.with_structured_output(ShoppingRequest)
    prompt = ChatPromptTemplate.from_messages([
        ("system", """Extract a structured shopping request from the user message.
Extract 1-3 specific meal names into meal_keywords — not individual ingredients.
For dietary_restrictions: only explicit restrictions the user stated.
Defaults: zip_code='94103', servings=4.

budget_usd: extract dollar amounts like 'under $40', 'budget $25' → float. Null if absent.
max_calories_per_serving: extract 'under 500 cal', '600 calories' → float. Null if absent.
dietary_profile: 'diabetic'→'diabetic', 'vegan'→'vegan', 'low-carb'→'low-carb',
  'keto'→'keto', 'gluten free'→'gluten-free', 'dairy free'→'dairy-free'. '' if absent.

preferred_retailer: 'walmart'→'walmart', 'target'→'target', 'costco'→'costco',
  'amazon'→'amazon', kroger family→'kroger'. Default 'kroger'."""),
        ("human", "{message}"),
    ])
    result = (prompt | structured_llm).invoke({"message": last_content})
    if isinstance(result, dict):
        result["raw_message"] = last_content
    else:
        result.raw_message = last_content
    return {"request": result, "agent_steps": ["parse_request"]}


# ── Node: find_store ──────────────────────────────────────────────────────────
def find_store(state: AgentState) -> dict:
    zip_code = _req(state, "zip_code", "94103")
    retailer = _get_retailer(state)
    if _uses_rapidapi(retailer):
        result = rapidapi_find_store.invoke({"zip_code": zip_code})
    else:
        result = kroger_find_store.invoke({"zip_code": zip_code})
    if result.get("error") or not result.get("location_id"):
        return {"location_id": None, "store_name": f"Online ({retailer.title()})"}
    steps = list(state.get("agent_steps", []))
    steps.append("find_store")
    return {
        "location_id": result["location_id"],
        "store_name": result.get("name", retailer.title()),
        "agent_steps": steps,
    }


# ── Node: supervisor ──────────────────────────────────────────────────────────
SUPERVISOR_PROMPT = """You are orchestrating a personal shopping assistant.
Look at the current state and decide what to do next.
Respond with EXACTLY one of these words — nothing else:

  nutrition_agent   — interpret dietary/health constraints into rules
  recipe_agent      — find matching recipes
  shopping_agent    — check store availability and prices
  budget_agent      — validate total cost against budget limit
  finish_node       — all done, present result

Decision rules (apply in order):
1. dietary_profile or max_calories set AND nutrition_status=unchecked → nutrition_agent
2. selected_recipes is empty → recipe_agent
3. ingredients list is empty → recipe_agent
4. shopping_list is empty → shopping_agent
5. budget_usd set AND budget_status=unchecked → budget_agent
6. budget_status=over AND iteration < 3 → recipe_agent
7. nutrition_status=fail AND iteration < 3 → recipe_agent
8. Everything looks good OR iteration >= 3 → finish_node

Current state:
{summary}
"""


def _summarise(state: AgentState) -> str:
    budget = _req(state, "budget_usd")
    profile = _req(state, "dietary_profile", "")
    calories = _req(state, "max_calories_per_serving")
    ingredients = state.get("ingredients", [])
    total = sum(
        (i.get("price") or 0) if isinstance(i, dict) else (i.price or 0)
        for i in ingredients
    )
    return (
        f"dietary_profile={profile or 'none'} | "
        f"max_calories={calories or 'none'} | "
        f"budget_usd={budget or 'none'} | "
        f"recipes={len(state.get('selected_recipes', []))} | "
        f"ingredients={len(ingredients)} | "
        f"shopping_list_built={len(state.get('shopping_list', [])) > 0} | "
        f"estimated_total=${total:.2f} | "
        f"budget_status={state.get('budget_status', 'unchecked')} | "
        f"nutrition_status={state.get('nutrition_status', 'unchecked')} | "
        f"violations={state.get('constraint_violations', [])} | "
        f"iteration={state.get('iteration', 0)}"
    )


def supervisor_node(state: AgentState) -> dict:
    iteration = state.get("iteration", 0)
    if iteration >= 3:
        decision = "finish_node"
    else:
        summary = _summarise(state)
        response = llm.invoke([
            SystemMessage(content=SUPERVISOR_PROMPT.format(summary=summary)),
            HumanMessage(content="What next?"),
        ])
        decision = response.content.strip().split()[0].lower()
        valid = {
            "nutrition_agent", "recipe_agent", "shopping_agent",
            "budget_agent", "finish_node",
        }
        if decision not in valid:
            decision = "finish_node"

    steps = list(state.get("agent_steps", []))
    steps.append(f"supervisor→{decision}")
    return {
        "next_agent": decision,
        "iteration": iteration + 1,
        "agent_steps": steps,
    }


def supervisor_router(state: AgentState) -> str:
    return state.get("next_agent", "finish_node")


# ── Node: nutrition_agent ─────────────────────────────────────────────────────
def nutrition_agent(state: AgentState) -> dict:
    profile = _req(state, "dietary_profile", "")
    max_cal = _req(state, "max_calories_per_serving")

    if not profile and not max_cal:
        steps = list(state.get("agent_steps", []))
        steps.append("nutrition_agent:skipped")
        return {
            "nutrition_status": "ok",
            "nutrition_constraints": {},
            "agent_steps": steps,
        }

    prompt = ChatPromptTemplate.from_messages([
        ("system", """Convert a dietary profile into concrete constraints.
Return JSON only — no markdown, no extra text.
Schema: {"max_carbs_g": number|null, "max_calories": number|null,
         "max_sugar_g": number|null, "avoid_ingredients": [strings], "notes": "string"}

Profiles:
  diabetic    → max_carbs_g:45, max_sugar_g:25, avoid:[sugar,honey,white rice,corn syrup]
  low-carb    → max_carbs_g:50, avoid:[bread,pasta,rice,potatoes,sugar]
  keto        → max_carbs_g:20, avoid:[bread,pasta,rice,sugar,fruit,beans]
  vegan       → avoid:[meat,chicken,fish,seafood,dairy,eggs,honey,gelatin]
  vegetarian  → avoid:[meat,chicken,fish,seafood]
  gluten-free → avoid:[wheat,barley,rye,bread,pasta,flour,soy sauce]
  dairy-free  → avoid:[milk,cheese,butter,cream,yogurt,whey]"""),
        ("human",
         "Profile: {profile}\nMax calories per serving: {calories}"),
    ])
    result = (prompt | llm).invoke({
        "profile": profile or "none",
        "calories": str(max_cal) if max_cal else "not specified",
    })
    try:
        constraints = json.loads(result.content.strip())
    except Exception:
        constraints = {"notes": result.content.strip()}
    if max_cal:
        constraints["max_calories"] = max_cal

    steps = list(state.get("agent_steps", []))
    steps.append("nutrition_agent")
    return {
        "nutrition_constraints": constraints,
        "nutrition_status": "ok",
        "agent_steps": steps,
    }


# ── Node: recipe_agent ────────────────────────────────────────────────────────
def recipe_agent(state: AgentState) -> dict:
    keywords = _req(state, "meal_keywords", [])
    restrictions = _req(state, "dietary_restrictions", [])
    profile = _req(state, "dietary_profile", "")

    diet_parts = list(restrictions)
    if profile and profile not in diet_parts:
        diet_parts.append(profile)
    diet = diet_parts[0] if diet_parts else ""

    budget_status = state.get("budget_status", "unchecked")
    iteration = state.get("iteration", 0)

    queries = []
    if keywords:
        words = keywords[0].strip().split()
        if len(words) >= 2:
            queries.append(" ".join(words[-2:]))
        queries.append(words[-1])
    queries.extend(["curry", "chicken", "pasta"])

    recipes = []
    for query in queries:
        if budget_status == "over" and iteration > 1:
            query = f"simple {query}"
        recipes = search_recipes.invoke({
            "query": query,
            "diet": diet,
            "max_ready_time": 90,
            "number": 3,
        })
        if recipes:
            break

    steps = list(state.get("agent_steps", []))
    steps.append(f"recipe_agent:iter{iteration}")
    return {
        "selected_recipes": recipes,
        "ingredients": [],
        "shopping_list": [],
        "budget_status": "unchecked",
        "agent_steps": steps,
    }


# ── Node: shopping_agent ──────────────────────────────────────────────────────
def shopping_agent(state: AgentState) -> dict:
    """Runs extract → availability → substitutions as one atomic step."""
    pantry = {
        p.lower().strip()
        for p in (_req(state, "pantry_items") or [])
    }
    seen: set[str] = set()
    all_ingredients: list = []

    for recipe in state.get("selected_recipes", []):
        data = get_recipe_ingredients.invoke({"recipe_id": recipe["id"]})
        for ing in data.get("ingredients", []):
            key = ing["name"].lower().strip()
            if key in seen or key in pantry:
                continue
            seen.add(key)
            all_ingredients.append(IngredientAvailability(
                name=ing["name"],
                original=ing["original"],
                aisle=ing.get("aisle", "General"),
                available=True,
            ))

    retailer = _get_retailer(state)
    location_id = state.get("location_id") or "00000000"
    updated: list = []

    for ing in all_ingredients:
        if _uses_rapidapi(retailer):
            result = rapidapi_check_availability.invoke({
                "ingredient": ing.name,
                "location_id": location_id,
                "store": retailer,
            })
        else:
            result = kroger_check_availability.invoke({
                "ingredient": ing.name,
                "location_id": location_id,
            })
        updated.append(ing.model_copy(update={
            "available": result.get("available", False),
            "product_description": result.get("product_description"),
            "price": result.get("price"),
        }))

    final: list = []
    for ing in updated:
        if ing.available:
            final.append(ing)
            continue
        subs = get_ingredient_substitutes.invoke(
            {"ingredient_name": ing.name}
        )
        chosen = (subs.get("substitutes") or ["Ask store staff"])[0]
        final.append(ing.model_copy(update={"substitute": chosen}))

    steps = list(state.get("agent_steps", []))
    steps.append("shopping_agent")
    return {
        "ingredients": final,
        "shopping_list": final,
        "agent_steps": steps,
    }


# ── Node: budget_agent ────────────────────────────────────────────────────────
def budget_agent(state: AgentState) -> dict:
    budget = _req(state, "budget_usd")
    if not budget:
        steps = list(state.get("agent_steps", []))
        steps.append("budget_agent")
        return {"budget_status": "ok", "agent_steps": steps}

    total = sum(
        (i.get("price") or 0) if isinstance(i, dict) else (i.price or 0)
        for i in state.get("ingredients", [])
    )
    violations = list(state.get("constraint_violations", []))

    steps = list(state.get("agent_steps", []))
    steps.append("budget_agent")

    if total > budget:
        msg = (
            f"Over budget by ${total - budget:.2f} "
            f"(total ${total:.2f}, limit ${budget:.2f})"
        )
        if msg not in violations:
            violations.append(msg)
        return {
            "budget_status": "over",
            "constraint_violations": violations,
            "agent_steps": steps,
        }

    return {
        "budget_status": "ok",
        "constraint_violations": violations,
        "agent_steps": steps,
    }


# ── Node: finish_node ─────────────────────────────────────────────────────────
def finish_node(state: AgentState) -> dict:
    ingredients = state.get("ingredients", [])
    recipes = state.get("selected_recipes", [])
    store = state.get("store_name", "your store")
    retailer = _get_retailer(state)

    if not ingredients:
        steps = list(state.get("agent_steps", []))
        steps.append("finish_node")
        return {
            "shopping_list": [],
            "messages": [AIMessage(content=(
                "I couldn't find recipes or ingredients for your request. "
                "Try rephrasing or choosing a different retailer."
            ))],
            "agent_steps": steps,
        }

    by_aisle: dict[str, list] = {}
    for ing in ingredients:
        aisle = (ing.get("aisle") if isinstance(ing, dict) else ing.aisle) or "Other"
        by_aisle.setdefault(aisle, []).append(ing)

    lines = [f"## 🛒 Shopping List — {store}\n"]
    recipe_titles = ", ".join(r.get("title", "") for r in recipes)
    lines.append(f"**Recipes:** {recipe_titles}\n")

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
                price_str = f" — ${price:.2f}" if price else ""
                desc_str = f" ({desc})" if desc else ""
                lines.append(f"- ✓ {orig}{desc_str}{price_str}")
                if price:
                    total += price
            else:
                sub_str = f" 💡 sub: *{sub}*" if sub else ""
                lines.append(f"- ✗ {orig} *(not available)*{sub_str}")

    lines.append("\n---")
    budget = _req(state, "budget_usd")
    profile = _req(state, "dietary_profile", "")
    violations = state.get("constraint_violations", [])
    iteration = state.get("iteration", 0)

    if total > 0:
        lines.append(f"\n**Estimated total:** ${total:.2f}")
        if budget:
            if state.get("budget_status") == "ok":
                lines.append(f"✅ Within budget (${budget:.2f} limit)")
            else:
                lines.append(f"⚠️ Over budget (${budget:.2f} limit)")

    if profile:
        status = state.get("nutrition_status", "unchecked")
        icon = "✅" if status == "ok" else "⚠️"
        lines.append(f"{icon} {profile.title()} profile applied")

    for v in violations:
        lines.append(f"⚠️ {v}")

    if iteration > 1:
        lines.append(f"ℹ️ Refined over {iteration} iterations")

    steps = list(state.get("agent_steps", []))
    steps.append("finish_node")

    return {
        "shopping_list": ingredients,
        "messages": [AIMessage(content="\n".join(lines))],
        "agent_steps": steps,
    }


# ── Graph assembly ─────────────────────────────────────────────────────────────
def build_graph():
    builder = StateGraph(AgentState)

    builder.add_node("receive_message", receive_message)
    builder.add_node("parse_request", parse_request)
    builder.add_node("find_store", find_store)
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("nutrition_agent", nutrition_agent)
    builder.add_node("recipe_agent", recipe_agent)
    builder.add_node("shopping_agent", shopping_agent)
    builder.add_node("budget_agent", budget_agent)
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

    # langgraph dev / platform handles persistence — no custom checkpointer
    return builder.compile()


graph = build_graph()
