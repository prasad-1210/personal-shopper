"""
Shared state models for the personal-shopper multi-agent system.

All agents and the supervisor use ``AgentState`` as the graph state schema.
``RemoteGraph`` passes this dict over HTTP between processes.
"""
from typing import Annotated, Any

from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


class ShoppingRequest(BaseModel):
    """Structured representation of a user meal-shopping request.

    Produced by the supervisor ``parse_request`` node via LLM structured output,
    optionally merged with UI sidebar defaults.

    Attributes:
        raw_message: Original user text including any UI constraint prefix.
        meal_keywords: One to three dish names (not individual ingredients).
        dietary_restrictions: Explicit restrictions stated in the message.
        servings: Number of portions; default 4.
        zip_code: US 5-digit zip for store lookup.
        pantry_items: Ingredients the user already has (excluded from shopping list).
        preferred_retailer: Store family — routes Kroger vs RapidAPI APIs.
        budget_usd: Maximum spend in USD, or None if unset.
        max_calories_per_serving: Per-serving calorie cap, or None.
        dietary_profile: Named profile (vegan, keto, diabetic, etc.) for nutrition agent.
    """

    raw_message: str
    meal_keywords: list[str] = Field(default_factory=list)
    dietary_restrictions: list[str] = Field(default_factory=list)
    servings: int = 4
    zip_code: str = "94103"
    pantry_items: list[str] = Field(default_factory=list)
    preferred_retailer: str = Field(default="kroger")
    budget_usd: float | None = None
    max_calories_per_serving: float | None = None
    dietary_profile: str = ""


class IngredientAvailability(BaseModel):
    """One shopping-list line with store availability and optional substitute.

    Attributes:
        name: Normalized ingredient name.
        original: Display text from recipe (amount + ingredient).
        aisle: Store aisle category for list grouping.
        available: Whether the product was found in stock/catalog.
        product_description: Matched product title from retailer API.
        price: Unit price in USD when known.
        substitute: Suggested replacement when unavailable.
    """

    name: str
    original: str
    aisle: str
    available: bool
    product_description: str | None = None
    price: float | None = None
    substitute: str | None = None


class AgentState(TypedDict):
    """Graph state shared across supervisor and all sub-agents.

    Each agent reads relevant fields and returns a partial update dict.
    Fields are merged by LangGraph (``messages`` uses ``add_messages`` reducer).

    Attributes:
        messages: Chat history; supervisor input/output uses HumanMessage/AIMessage.
        request: ShoppingRequest (dict or Pydantic) after parse_request.
        location_id: Kroger store ID or RapidAPI placeholder from find_store.
        store_name: Human-readable store name for the shopping list header.
        selected_recipes: Recipe dicts from recipe agent (id, title, servings, …).
        ingredients: IngredientAvailability list after shopping agent.
        shopping_list: Same as ingredients when flow completes successfully.
        confirmed: Reserved for future human-in-the-loop confirmation.
        error: Technical error string when a sub-agent or tool fails.
        nutrition_constraints: JSON rules from nutrition agent.
        budget_status: ``unchecked`` | ``ok`` | ``over``.
        nutrition_status: ``unchecked`` | ``ok`` | ``fail``.
        constraint_violations: Human-readable budget/constraint messages.
        iteration: Supervisor loop counter; reset each new user message.
        refinement_count: Budget/nutrition recipe retry counter.
        next_agent: Router target set by supervisor_node.
        agent_steps: Ordered progress trail for UI and debugging.
    """

    messages: Annotated[list[Any], add_messages]
    request: Any
    location_id: str | None
    store_name: str | None
    selected_recipes: list[dict[str, Any]]
    ingredients: list[Any]
    shopping_list: list[Any]
    confirmed: bool
    error: str | None
    nutrition_constraints: Any
    budget_status: str
    nutrition_status: str
    constraint_violations: list[str]
    iteration: int
    refinement_count: int
    next_agent: str
    agent_steps: list[str]
