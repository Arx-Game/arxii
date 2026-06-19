"""Crafting submodule for the items app.

Provides the generic magical-crafting framework: recipes, ingredient slots,
attempt tracking, and cost consumption. All models carry ``Meta.app_label = "items"``
so Django discovers them under the ``items`` app label.
"""
