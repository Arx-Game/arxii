# Crafting

Arx I featured intricate crafting trees defined directly in code. Rather than porting every old recipe we will rebuild the system with a data first approach. Recipes and workshops live in the database so designers can iterate without changing source.

Key ideas:

1. Define crafting steps in data so resources can be checked and items generated without code changes.
2. Keep the feel of skill gates and rare components but configure them in data tables.
3. Encourage collaboration by allowing characters to combine efforts on large projects.

This rewrite aims for smoother experimentation and a more social crafting experience.
