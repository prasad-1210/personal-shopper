"""
Shared state models for personal-shopper multi-agent system.
Imported by all agents and the supervisor.
"""
from typing import Annotated, Any

from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


class ShoppingRequest(BaseModel):
    """Structured form of the user meal request."""
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
    name: str
    original: str
    aisle: str
    available: bool
    product_description: str | None = None
    price: float | None = None
    substitute: str | None = None


class AgentState(TypedDict):
    """Shared state across all agents. Each agent reads and writes its fields."""
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
    iteration: int                    # supervisor loop counter (reset each new message)
    refinement_count: int             # budget retry counter
    next_agent: str
    agent_steps: list[str]
