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
- Pledges (#4333 slice 2). `components/PledgeDialog.tsx` (Pledge yourself: the pledge type's
  staff-authored text, its favor target, the system-generated `ServiceTermsList` of what earns
  favor with the earning rate, an optional prayer; dispatches `pledge_take`),
  `components/SacrificeDialog.tsx` (items the character carries; dispatches `sacrifice`, which
  the server refuses away from a shrine or temple), `components/PledgeCard.tsx` (the sheet's
  pledge in three labelled parts, each credit with its calculation, and Close once the target
  is met; dispatches `pledge_close`). `WorshipSection` shows the newest pledge card and the
  owner's Pray / Sacrifice / Pledge yourself doors; the room panel's
  `game/components/room-panel/HolySiteBlock.tsx` shows them for the being whose shrine or
  temple the character stands in. Reads `/api/worship/pledges/`, `/api/worship/pledge-cards/`,
  `/api/worship/beings/{id}/service-terms/` and `/api/worship/beings/holy-site/`.
  `pledgeText.ts` builds the earning-rate parts and the time left.
- Answers (#4333 slice 3). A closed pledge's answer arrives as an ordinary vision;
  `components/VisionCard.tsx` footnotes the fact clue (`clue_name`), the follow-up
  (`follow_up_footnote`, "A mission came with it: ..." for a mission clue) and the cost's conditions (`condition_names`), never as controls.
