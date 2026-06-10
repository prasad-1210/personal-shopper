Convert a dietary profile into concrete constraints.
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
  dairy-free  → avoid:[milk,cheese,butter,cream,yogurt,whey]
