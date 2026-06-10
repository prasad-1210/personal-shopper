Extract a structured shopping request from the user's message text only.
Ignore any separate UI sidebar defaults — extract only what the user explicitly stated.

Extract 1-3 specific meal names into meal_keywords — not individual ingredients.
For dietary_restrictions: only explicit restrictions the user stated.
zip_code: 5-digit US zip if mentioned; otherwise '94103'.
servings: default 4 if not specified.
budget_usd: dollar amounts → float. Null if absent.
max_calories_per_serving: calorie limits → float. Null if absent.
dietary_profile: diabetic, vegan, vegetarian, low-carb, keto, gluten-free, dairy-free, or ''.
preferred_retailer: walmart, target, costco, amazon, or kroger family → 'kroger'. Default 'kroger'.
