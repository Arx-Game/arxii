# Worship (frontend)

Prayers and visions (#3779) on the character sheet.

- `components/WorshipSection.tsx` — the sheet card: public faith, the character's visions, the
  owner's `PrayDialog`, and for staff the recent prayers with `SendVisionDialog` beside them.
- `components/VisionCard.tsx` + `visionStyle.ts` — the one treatment reserved for visions. The
  game feed's `vision` kind (`game/components/FeedNoteBlock.tsx`) uses the same tokens at the
  delivery moment; nothing else may.
- `api.ts` / `queries.ts` — `/api/worship/visions/`, `/api/worship/prayers/`, the staff POST, and
  the `pray` action dispatched through the registry seam as the character.
