# Worship (frontend)

Prayers and visions (#3779) on the character sheet.

- `components/WorshipSection.tsx` — the sheet card: public faith, the character's visions, the
  owner's `PrayDialog`, and for staff the recent prayers with `SendVisionDialog` beside them.
- `components/VisionCard.tsx` + `visionStyle.ts` — the one treatment reserved for visions. The
  game feed's `vision` kind (`game/components/FeedNoteBlock.tsx`) uses the same glyph and
  frame at the delivery moment, with its text in the reader's Display settings (#4330), not
  `VISION_TEXT_CLASS`; nothing else may use the treatment.
- `api.ts` / `queries.ts` — `/api/worship/visions/`, `/api/worship/prayers/`, the staff POST, and
  the `pray` action dispatched through the registry seam as the character.
- `components/CallOnFavor.tsx` (#4333) — the Call on favor control beside a check: a mission
  option (`missions/components/BeatCard.tsx`, `GroupBeatCard.tsx`), the scene self-check
  (`scenes/components/SelfCheckPanel.tsx`) and the scene Actions panel (`inline`, since that
  host is a popover). The picker reads `useInvocationOptions` (`GET /api/worship/beings/
invocation-options/`): per being the difficulty with each ease, uses left, the bonus by
  result, or the reason it is refused. The choice rides the check's request; nothing rolls in
  the picker. `invocationText.ts` builds the bonus line.
