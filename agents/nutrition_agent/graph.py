"""
Nutrition Agent — interprets dietary profile into concrete constraints.
Deployed as a standalone LangGraph server on port 22001 (local dev).
Called by supervisor via RemoteGraph.
"""
import json

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from shared.distributed_tracing import export_traced_graph
from shared.state import AgentState

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


def interpret_constraints(state: AgentState) -> dict:
    """Interpret dietary profile into concrete nutrition rules."""
    req = state.get("request") or {}
    profile = req.get("dietary_profile", "") if isinstance(req, dict) \
        else getattr(req, "dietary_profile", "")
    max_cal = req.get("max_calories_per_serving") if isinstance(req, dict) \
        else getattr(req, "max_calories_per_serving", None)

    steps = list(state.get("agent_steps", []))

    if not profile and not max_cal:
        steps.append("nutrition_agent:skipped")
        return {
            "nutrition_status": "ok",
            "nutrition_constraints": {},
            "agent_steps": steps,
        }

    prompt = ChatPromptTemplate.from_messages([
        ("system", """Convert a dietary profile into concrete constraints.
Return JSON only — no markdown, no extra text.
Schema: {{"max_carbs_g": number|null, "max_calories": number|null,
         "max_sugar_g": number|null,
         "avoid_ingredients": [strings],
         "notes": "string"}}

Profiles:
  diabetic    → max_carbs_g:45, max_sugar_g:25,
                avoid:[sugar,honey,white rice,corn syrup,potatoes]
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

    steps.append("nutrition_agent")
    return {
        "nutrition_constraints": constraints,
        "nutrition_status": "ok",
        "agent_steps": steps,
    }


def build_graph():
    builder = StateGraph(AgentState)
    builder.add_node("interpret_constraints", interpret_constraints)
    builder.add_edge(START, "interpret_constraints")
    builder.add_edge("interpret_constraints", END)
    return builder.compile()


_compiled_graph = build_graph()
graph = export_traced_graph(_compiled_graph, "nutrition_agent")
