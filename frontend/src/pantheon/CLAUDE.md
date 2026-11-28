# Pantheon (Deity Editor, #3780)

Staff-only authoring of the pantheon over `/api/worship/admin/beings/`.

- `pages/PantheonListPage.tsx` — `/staff/pantheon`: tile grid sorted by pool, search, tier filter.
- `pages/BeingEditPage.tsx` — `/staff/pantheon/new` and `/staff/pantheon/:id/edit`: one long
  page of collapsible `EditorSection`s with highlight dots; every "+ Add" carries its
  explanation as a `title` tooltip; Save is live.
- `pages/BeingDashboardPage.tsx` — `/staff/pantheon/:id`: pool + Send Vision in the header,
  tabs Overview / Worship / Temples & Shrines / Prayers / Visions / Relics / Codex Entries.
  Overview's "Pledges and answers" card (#4333) counts pledge types, answers and held answers
  and links the two admin builders; the Visions tab lists answers held until the pool can pay
  (`useHeldAnswers`, `/api/worship/admin/beings/{id}/held-answers/`).
- Staff-page conventions only (plain cards, `container mx-auto max-w-6xl px-4 py-8`); never
  the realm-themed fonts.

## Unsaved typing survives a closed tab

The edit page holds every field in the tab's memory and sends the whole page on Save, so a
closed tab used to lose a half-written god. `useUnsavedDraft.ts` copies the working draft to
`localStorage` (key `arxii:unsaved-draft:pantheon-being:<id|new>`) while it differs from the
server's page, restores it on reopen with a "Discard them" action, warns before the tab closes
with unsaved changes, and forgets the copy once Save succeeds. It only ever fills the form:
nothing goes live until Save. When the server's page changed since the copy was started
(another editor saved), the copy is not applied on its own, because the next Save would
overwrite their work; a toast offers "Restore mine" instead. The copy lives in one browser, so
it does not follow a person to another machine.

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
