"""
Seed LangSmith datasets with baseline examples.

Usage:
    python tests/eval/seed_datasets.py

Requires LANGSMITH_API_KEY in environment.

Creates three datasets:
    request-parsing-v1        — parse_request node
    recipe-relevance-v1       — recipe_agent node
    substitution-quality-v1   — shopping_agent substitutions
"""
import sys

sys.path.insert(0, ".")

from langsmith import Client

DATASETS = {
    "request-parsing-v1": {
        "description": "Parse user utterance → structured ShoppingRequest fields",
        "examples": [
            {
                "input": {"utterance": "Thai green curry for 4 people near 75035"},
                "output": {
                    "zip_code": "75035",
                    "servings": 4,
                    "meal_keywords_contains": "curry",
                    "dietary_profile": "",
                    "budget_usd": None,
                },
            },
            {
                "input": {"utterance": "vegan pasta near 94103, budget $30"},
                "output": {
                    "zip_code": "94103",
                    "dietary_profile": "vegan",
                    "budget_usd": 30.0,
                    "meal_keywords_contains": "pasta",
                },
            },
            {
                "input": {
                    "utterance": (
                        "[Retailer: kroger | Diet: diabetic | Budget: $50 | "
                        "Servings: 2]\n\npalak paneer near 75035"
                    )
                },
                "output": {
                    "zip_code": "75035",
                    "servings": 2,
                    "dietary_profile": "diabetic",
                    "budget_usd": 50.0,
                    "preferred_retailer": "kroger",
                },
            },
            {
                "input": {"utterance": "low carb chicken dinner for 2"},
                "output": {
                    "servings": 2,
                    "dietary_profile": "low-carb",
                    "meal_keywords_contains": "chicken",
                },
            },
            {
                "input": {"utterance": "gluten free pizza, I shop at target, near 10001"},
                "output": {
                    "zip_code": "10001",
                    "dietary_profile": "gluten-free",
                    "preferred_retailer": "target",
                },
            },
            {
                "input": {"utterance": "make something for dinner"},
                "output": {
                    "zip_code": "94103",
                    "servings": 4,
                },
            },
            {
                "input": {
                    "utterance": (
                        "I have chicken and garlic at home, "
                        "need ingredients for pasta carbonara, 4 servings"
                    )
                },
                "output": {
                    "servings": 4,
                    "pantry_items_contains": ["chicken", "garlic"],
                    "meal_keywords_contains": "carbonara",
                },
            },
            {
                "input": {"utterance": "keto beef stew under $60 near 33101"},
                "output": {
                    "zip_code": "33101",
                    "dietary_profile": "keto",
                    "budget_usd": 60.0,
                    "meal_keywords_contains": "beef",
                },
            },
            {
                "input": {
                    "utterance": (
                        "[Retailer: walmart | Max calories: 500/serving | Servings: 3]\n\n"
                        "tofu stir fry"
                    )
                },
                "output": {
                    "servings": 3,
                    "max_calories_per_serving": 500.0,
                    "preferred_retailer": "walmart",
                    "meal_keywords_contains": "tofu",
                },
            },
            {
                "input": {"utterance": "dairy free dessert for a party"},
                "output": {
                    "dietary_profile": "dairy-free",
                },
            },
        ],
    },
    "recipe-relevance-v1": {
        "description": "Recipe search results match user request and constraints",
        "examples": [
            {
                "input": {
                    "request": "Thai green curry",
                    "diet": "",
                    "avoid_ingredients": [],
                },
                "output": {
                    "criterion": "At least one recipe involves curry or Thai cuisine",
                },
            },
            {
                "input": {
                    "request": "pasta carbonara",
                    "diet": "vegetarian",
                    "avoid_ingredients": ["meat", "chicken", "fish", "seafood"],
                },
                "output": {
                    "criterion": (
                        "Recipes should be pasta-based and vegetarian-friendly. "
                        "Meat, chicken, fish, seafood should not appear as main ingredients."
                    ),
                },
            },
            {
                "input": {
                    "request": "palak paneer",
                    "diet": "vegetarian",
                    "avoid_ingredients": [],
                },
                "output": {
                    "criterion": (
                        "At least one recipe is an Indian spinach and cheese dish. "
                        "Should not contain meat."
                    ),
                },
            },
            {
                "input": {
                    "request": "chicken dinner",
                    "diet": "keto",
                    "avoid_ingredients": ["bread", "pasta", "rice", "sugar"],
                },
                "output": {
                    "criterion": (
                        "Recipes should feature chicken as main protein. "
                        "Avoid bread, pasta, rice as main carb sources."
                    ),
                },
            },
            {
                "input": {
                    "request": "vegan tacos",
                    "diet": "vegan",
                    "avoid_ingredients": ["meat", "chicken", "dairy", "eggs"],
                },
                "output": {
                    "criterion": (
                        "Recipes should be taco-based and plant-based. "
                        "No meat, dairy, or eggs as ingredients."
                    ),
                },
            },
        ],
    },
    "substitution-quality-v1": {
        "description": "Substitution suggestions are culinarily appropriate",
        "examples": [
            {
                "input": {
                    "unavailable_ingredient": "lemongrass",
                    "recipe_context": "Thai green curry",
                    "dietary_profile": "",
                },
                "output": {
                    "criterion": (
                        "Substitute should provide citrus/aromatic flavour. "
                        "Lemon zest + ginger is acceptable. "
                        "A completely unrelated ingredient is not acceptable."
                    ),
                },
            },
            {
                "input": {
                    "unavailable_ingredient": "galangal",
                    "recipe_context": "Thai soup",
                    "dietary_profile": "",
                },
                "output": {
                    "criterion": (
                        "Substitute should be a root spice. "
                        "Fresh ginger is acceptable. "
                        "Non-spice substitutes are not acceptable."
                    ),
                },
            },
            {
                "input": {
                    "unavailable_ingredient": "paneer",
                    "recipe_context": "palak paneer",
                    "dietary_profile": "vegetarian",
                },
                "output": {
                    "criterion": (
                        "Substitute must be vegetarian. "
                        "Tofu or halloumi are acceptable. "
                        "Meat is not acceptable."
                    ),
                },
            },
            {
                "input": {
                    "unavailable_ingredient": "fish sauce",
                    "recipe_context": "Thai curry",
                    "dietary_profile": "vegan",
                },
                "output": {
                    "criterion": (
                        "Substitute must be vegan. "
                        "Soy sauce + lime or tamari are acceptable. "
                        "Any seafood-based substitute is not acceptable for vegan."
                    ),
                },
            },
            {
                "input": {
                    "unavailable_ingredient": "heavy cream",
                    "recipe_context": "pasta sauce",
                    "dietary_profile": "dairy-free",
                },
                "output": {
                    "criterion": (
                        "Substitute must be dairy-free. "
                        "Coconut cream or cashew cream are acceptable. "
                        "Any dairy product is not acceptable for dairy-free."
                    ),
                },
            },
        ],
    },
}


def seed_all():
    client = Client()

    for dataset_name, dataset_def in DATASETS.items():
        print(f"\nSeeding dataset: {dataset_name}")

        existing = list(client.list_datasets(dataset_name=dataset_name))
        if existing:
            dataset = existing[0]
            print(f"  Dataset exists (id={dataset.id})")
        else:
            dataset = client.create_dataset(
                dataset_name=dataset_name,
                description=dataset_def["description"],
            )
            print(f"  Created dataset (id={dataset.id})")

        existing_examples = list(client.list_examples(dataset_id=dataset.id))
        existing_inputs = [e.inputs for e in existing_examples]

        added = 0
        for example in dataset_def["examples"]:
            if example["input"] not in existing_inputs:
                client.create_example(
                    inputs=example["input"],
                    outputs=example["output"],
                    dataset_id=dataset.id,
                )
                added += 1

        print(f"  Added {added} new examples ({len(existing_examples)} already existed)")

    print("\nDone. All datasets seeded.")


if __name__ == "__main__":
    seed_all()
