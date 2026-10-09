# Pantheon (Deity Editor, #3780)

Staff-only authoring of the pantheon over `/api/worship/admin/beings/`.

- `pages/PantheonListPage.tsx` — `/staff/pantheon`: tile grid sorted by pool, search, tier filter.
- `pages/BeingEditPage.tsx` — `/staff/pantheon/new` and `/staff/pantheon/:id/edit`: one long
  page of collapsible `EditorSection`s with highlight dots; every "+ Add" carries its
  explanation as a `title` tooltip; Save is live.
- `pages/BeingDashboardPage.tsx` — `/staff/pantheon/:id`: pool + Send Vision in the header,
  tabs Overview / Worship / Temples & Shrines / Prayers / Visions / Relics / Codex Entries.
- Staff-page conventions only (plain cards, `container mx-auto max-w-6xl px-4 py-8`); never
  the realm-themed fonts.

## Facets on the edit page (#4197)

"Favored facets" picks through the shared `FacetPicker` (`@/magic/components/FacetPicker`),
`canCreate` for staff: a spelling that resolves to nothing shows what it is near, then
offers to create it in the same gesture. A created facet is not in `useEditorOptions` yet,
so the pick handler invalidates `pantheonKeys.options`.

## Tarot and relationships on the edit page (#4198)

The Tarot picker offers each card both ways up ("The Tower" / "The Tower, reversed"); a
picked card is offered neither way, since the link is one row per card with an
orientation (`tarot_cards: [{card, is_reversed}]`). A relationship line carries `story`:
this god's own telling, written to its own side of the shared row; the other god's side
is edited on the other god's page and never from here. What the Codex draws from these
rows is `codex/components/Companion.tsx`.
