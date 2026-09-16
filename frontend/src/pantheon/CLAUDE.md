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
