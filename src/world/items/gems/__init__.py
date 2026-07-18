"""Gemstone value model — Build 0b slice 1.

Gem types are ordinary ``ItemTemplate`` rows decorated by a ``GemDetails`` sidecar
(so they can be required/consumed like any material); a cut gem instance is an
``ItemInstance`` decorated by ``GemInstanceDetails`` carrying its size/purity/cut
grades. Worth = ``template.value × size × purity × cut``, folded into ``appraise()``.

All models set ``Meta.app_label = "items"`` so Django registers them under the
existing ``items`` app (no new Django app), mirroring ``world.items.crafting``.
"""
