# 0199 — Concealment defaults on; exposure is cut, material, or performed

**Status:** Accepted (2026-08-05, Apostate's rulings during the #2985 design session)

Worn-layer visibility is ONE top-down walk per body region with one predicate:
a layer is *see-through* when its cut exposes beneath
(`Silhouette.exposes_beneath` — the crafter's pick at making), its material is
sheer (`ItemTemplate.is_revealing`), or it is worn open
(`EquippedItem.opened_at` — the show verb). A plain garment **conceals what
lies beneath it by default**; the outermost layer always shows; deeper layers
show iff everything above them is see-through; skin (and its markings, and the
sun's reach) is just what you find when you run out of layers — no
skin-specific flag exists. ACCESSORY-layer pieces never conceal beneath: they
adorn a region, they don't blanket it.

Three surfaces this replaced: the per-slot `TemplateSlot.covers_lower_layers`
flag (show-by-default inverted the physical intuition and pushed a per-slot
authoring chore onto every template), the `revealed_at` state on the hidden
thing (#2965's item flag and #3007's marking flag — both patched asymmetries:
re-equip clearing, item-vs-marking scoping, reveal outliving its concealment),
and the short-lived `exposes_skin` (a special case of exposes-beneath — the
slit gown over stockings shows stockings, over nothing shows skin). Rejected:
a separate "shows garments beneath" axis distinct from "shows skin" (one cut
property drives both because the walk recurses), and per-craft revealing
toggles outside the silhouette (redundant with the cut and permits nonsense
states). The show/conceal verbs (aliases: reveal/cover) are declarative —
the player names the body part, piece, or marking; the walk computes which
covering garments open — and dressing at a region closes it back up.
Layer-count limits need no mechanism: the fixed per-(region, layer) equip
grid already caps the stack. Refines ADR-0194 (its accents/prestige/legend
split is unchanged; only the visibility walk beneath it moved).
